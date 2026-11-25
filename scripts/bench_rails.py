#!/usr/bin/env python3
"""Offline §8 benchmark; see docs/rails-performance.md for the workload and commands."""
import argparse
import contextlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import secrets
import select
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
BB = ROOT / 'bundlebees/contrib'
ORBIT = ROOT / 'orbitdesktop'
LANES, PAGE, BATCH = 10, 500, 50
MISSING = 'offline-worker'
RENDERER_CAP = 2000
FIXED_HISTORY_INDEX_BASE = 1000
# The live view answers at most LIVE_VIEW_LIMIT marks per selector (the shared query's
# default limit). A window holds its gap mark plus two probes per cycle, so it may plan
# at most LIVE_CYCLES_MAX cycles; longer windows spread them out instead of adding more.
LIVE_VIEW_LIMIT = 100
LIVE_CYCLES_MAX = (LIVE_VIEW_LIMIT - 1) // 2
# The service must import Orbit's vendored runtime, not a cached canonical module.
sys.path.insert(0, str(ORBIT / 'contrib' if sys.argv[1:2] == ['--reader'] else BB))
from rizzstack_rails import RailsLedger, query


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def rss(pid=None):
    fields = Path(f'/proc/{pid or "self"}/status').read_text().splitlines()
    return {name: int(next(line.split()[1] for line in fields if line.startswith(name + ':')))
            for name in ('VmRSS', 'VmHWM')}


def p95(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1]


def ms(start):
    return round((time.monotonic() - start) * 1000, 3)


def snapshot(path, doc):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(doc, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def check_ids(actual, expected):
    if len(set(actual)) != len(actual) or actual != expected:
        raise ValueError('duplicate, missing, out-of-order or unexpected event ID')


def fixed_history_seed(held):
    if held < 0:
        raise ValueError('held marks cannot be negative')
    return max(0, RENDERER_CAP - held)


def schedule(duration):
    width = duration / 6
    count = max(1, min(LIVE_CYCLES_MAX, int(width // 10)))
    for window in range(6):
        for n in range(count):
            yield window, width * (window + n / count)


def candidate(lane, n, *, live=None, gap=False):
    key = f'row-{lane}-{n}' if live is None else f'probe-{live}-{n}'
    body = dict(kind='tool.finish', source=dict(adapter='bench', instance='guest', record_id=key, revision='v1'),
                lane={'lane_id': f'lane-{lane}'}, scope={'campaign_id':'campaign',
                    'job_id': 'seed' if live is None else f'live-{live}', 'attempt_id':f'attempt-{lane}' if live is None else f'live-{live}'},
                authority='worker_report', dedupe_key=key, timing_quality='measured', duration_ms=n % 3000,
                payload={'call_id':key,'tool_name':'shell','command_family':'git','outcome':'ok','summary':'ok','evidence_ref':None})
    if gap:
        body.update(kind='source.gap', payload=dict(source_id=MISSING, range_start=1, range_end=1,
                    cursor=None, count=1, digest='b'*64, code='gap'), duration_ms=None, timing_quality='unknown')
    if live is not None:
        body['occurred_at'] = f'2026-01-01T00:{n//60:02d}:{n%60:02d}.000000Z'
    return body


def producer(path, lane, count, barrier):
    db = RailsLedger(path)
    blocks = []
    try:
        for start in range(0, count, BATCH):
            # All ten independent connections submit a transaction each round.
            barrier.wait(timeout=60)
            def batch(conn):
                seqs = [db._append_locked(conn, **candidate(lane, n, gap=n % PAGE == 0),
                         occurred_at=None, redaction_policy=None)['seq'] for n in range(start, start + BATCH)]
                if seqs != list(range(seqs[0], seqs[0] + BATCH)):
                    raise RuntimeError('non-contiguous writer receipts')
                return seqs[0]
            blocks.append(db._write_tx(batch))
        (path.parent / f'lane-{lane}.json').write_text(json.dumps(blocks))
    finally:
        db.close()


ATTEMPT_INDEX = 'rails_local_attempt_scan'


def index_mode(args):
    if args.migrate_attempt_index: return 'migrated'
    if args.no_attempt_index: return 'none'
    return 'default'


def has_attempt_index(path):
    with contextlib.closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT 1 FROM sqlite_schema WHERE type='index' AND name=?", (ATTEMPT_INDEX,)).fetchone() is not None


def drop_attempt_index(path):
    if not has_attempt_index(path):
        raise ValueError('local-attempt index is absent')
    with contextlib.closing(sqlite3.connect(path)) as db:
        db.execute(f'DROP INDEX {ATTEMPT_INDEX}')
        db.commit()
    if has_attempt_index(path):
        raise ValueError('local-attempt index is still present after drop')


def check_arm(index_mode, present):
    if index_mode not in ('default', 'none', 'migrated'):
        raise ValueError('unknown attempt-index mode')
    if present != (index_mode != 'none'):
        raise ValueError(f'{index_mode} arm has unexpected local-attempt index state')


def unindex_after_seed(path):
    if has_attempt_index(path):
        drop_attempt_index(path)


def seed(path, total, *, index_mode='default'):
    if index_mode not in ('default', 'none', 'migrated'):
        raise ValueError('unknown attempt-index mode')
    with contextlib.closing(RailsLedger(path)) as first:
        ledger_uuid = first.ledger_uuid
    if not has_attempt_index(path):
        raise ValueError('a new benchmark ledger did not create the local-attempt index')
    if index_mode in ('none', 'migrated'):
        drop_attempt_index(path)
    ctx = mp.get_context('spawn')
    barrier = ctx.Barrier(LANES)
    jobs = [ctx.Process(target=producer, args=(path,i,total//LANES,barrier)) for i in range(LANES)]
    start = time.monotonic()
    try:
        for proc in jobs: proc.start()
        for proc in jobs: proc.join()
        if any(p.exitcode != 0 for p in jobs): raise RuntimeError('concurrent seeder failed')
    finally:
        for proc in jobs:
            if proc.is_alive(): proc.terminate(); proc.join()
    blocks = [json.loads((path.parent / f'lane-{i}.json').read_text()) for i in range(LANES)]
    if sorted(s for lane in blocks for s in lane) != list(range(1,total+1,BATCH)):
        raise ValueError('seed receipt coverage failed')
    with contextlib.closing(sqlite3.connect(path)) as db:
        if db.execute('SELECT COUNT(*), COUNT(DISTINCT event_id) FROM event_rows').fetchone() != (total,total):
            raise ValueError('seed count or uniqueness failed')
    if index_mode in ('none', 'migrated'):
        unindex_after_seed(path)
    stats = dict(elapsed_ms=ms(start), db_bytes=path.stat().st_size, writer_pids=[p.pid for p in jobs],
                 events_per_lane=[len(b)*BATCH for b in blocks], unique_seed_ids=total, transaction_rows=BATCH,
                 index_mode=index_mode)
    if index_mode == 'migrated':
        installer = ROOT / 'bundlebees/scripts/rails_attempt_index.py'
        started = time.monotonic()
        result = subprocess.check_output([sys.executable, '-B', str(installer), str(path),
                                          '--ledger-uuid', ledger_uuid], text=True, timeout=20).strip()
        stats['migrate_ms'] = ms(started)
        if result != 'installed': raise ValueError('index was not installed on the benchmark ledger')
    stats['index_present_after_seed'] = has_attempt_index(path)
    check_arm(index_mode, stats['index_present_after_seed'])
    return blocks, stats


def reads(path, samples, blocks, save):
    """Time the first 500-limit call and the entire logical 500-row page independently."""
    db = RailsLedger(path, read_only=True)
    out = {'rss_start_kib':rss(), 'series':{}, 'pragmas':{k:db.query('PRAGMA '+k)[0][k] for k in
           ('page_size','cache_size','journal_mode','query_only')}}
    overview = None
    try:
        for name, call in [('events', query.query_events), ('view', query.query_view_page)]:
            series = out['series'][name] = {'samples':[]}
            cursors = [None] * LANES
            offsets = [0] * LANES
            for i in range(-LANES, max(samples, 5) if name == 'view' else samples):
                lane = i % LANES
                offset = offsets[lane]
                after = cursors[lane]
                expected = [f'{db.chain_id}:{blocks[lane][n//BATCH]+n%BATCH}' for n in range(offset,offset+PAGE)]
                sample = dict(lane=lane, offset=offset, first_id=expected[0], last_id=expected[-1], calls=[])
                ids, marks, missing = [], [], set()
                start = time.monotonic()
                while len(ids) < PAGE:
                    req = query.make_request('attempt',f'attempt-{lane}',format='json',after=after,limit=PAGE-len(ids))
                    t = time.monotonic()
                    result = call(req, db)
                    wire = query.wire_json(result).encode('ascii')
                    latency = ms(t)
                    if name == 'events':
                        items = result['items']
                    else:
                        view = result['items'][0]
                        if len(view['lanes']) != 1 or view['lanes'][0]['lane_id'] != f'lane-{lane}':
                            raise ValueError('incorrect view lane')
                        items = view['lanes'][0]['marks']; marks.extend(items)
                    actual = [item['event_id'] for item in items]
                    if not 0 < len(actual) <= req['limit'] or len(wire) > req['max_bytes']:
                        raise ValueError('wire bound or progress failed')
                    check_ids(actual, expected[len(ids):len(ids)+len(actual)])
                    ids.extend(actual); missing.update(result['missing_sources'])
                    after = result['next_cursor']
                    if result['completeness'] != 'partial' or 'coverage_unconfirmed' not in result['warnings']:
                        raise ValueError('coverage lost')
                    if bool(after) != (offset+len(ids) < len(blocks[lane])*BATCH):
                        raise ValueError('continuation coverage failed')
                    sample['calls'].append(dict(limit=req['limit'],rows=len(actual),bytes=len(wire),ms=latency))
                    if i < 0: break  # discard one physical first-page warm-up per lane
                if i < 0: continue
                sample['logical_500_ms'] = ms(start)
                check_ids(ids, expected)
                if MISSING not in missing: raise ValueError('explicit source gap absent')
                sample['missing_sources'] = sorted(missing)
                cursors[lane], offsets[lane] = after, offset+PAGE if after else 0
                if i < samples: series['samples'].append(sample)
                if name == 'view' and i < 5:
                    if overview is None: overview = {**view, 'lanes':[], 'missing_sources':[MISSING]}
                    overview['lanes'].append({**view['lanes'][0], 'marks':marks, 'source_status':'stale'})
                if i % 10 == 0: save(out)
            rows = series['samples']
            series.update(p95_single_query_ms=p95([s['calls'][0]['ms'] for s in rows]),
                          p95_logical_500_ms=p95([s['logical_500_ms'] for s in rows]),rss_end_kib=rss())
            save(out)
        return out, overview
    finally:
        db.close()


def get_message(proc, timeout=30):
    # Binary unbuffered pipes: one acknowledgement per request. Bound stalls, size and EOF.
    if not select.select([proc.stdout],[],[],timeout)[0]: raise TimeoutError('fixture acknowledgement')
    line = proc.stdout.readline(8192)
    if not line.endswith(b'\n'): raise RuntimeError('fixture exited or sent oversized response')
    return json.loads(line)


def send(proc, data):
    proc.stdin.write((json.dumps(data,separators=(',',':'))+'\n').encode()); proc.stdin.flush()


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try: proc.wait(5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    for pipe in [proc.stdout, proc.stdin]:
        if pipe: pipe.close()


def soak(path, duration, overview, args, save):
    tmp = path.parent
    cred = tmp/'read-token'; cred.touch(mode=0o600); cred.write_text(secrets.token_urlsafe(32))
    env = dict(PATH=os.environ['PATH'], HOME=str(tmp), TMPDIR=str(tmp), PYTHONDONTWRITEBYTECODE='1')
    with contextlib.ExitStack() as cleanup:
        reader = subprocess.Popen([sys.executable,'-B',str(SCRIPT),'--reader',str(path),str(cred)],env=env,
                                  stdout=subprocess.PIPE,bufsize=0)
        cleanup.callback(stop, reader)
        port = get_message(reader)
        js = subprocess.Popen(['node',str(SCRIPT.with_suffix('.mjs'))],env=env,cwd=tmp,
                              stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        cleanup.callback(stop, js)
        send(js,dict(orbit=str(ORBIT),modules=str(args.node_modules),chrome=str(args.chromium),
                     port=port,cred=str(cred),overview=overview))
        out = {'browser':get_message(js), 'cycles':[], 'windows':[], 'reader_start_kib':rss(reader.pid)}
        save(out)
        writer = RailsLedger(path); cleanup.callback(writer.close)
        if args.fixed_history:
            seeded = fixed_history_seed(0)
            for held in range(seeded):
                receipt = writer.append(**candidate(0, FIXED_HISTORY_INDEX_BASE + held, live=0))
                if receipt['duplicated']: raise ValueError('duplicate append')
            out['fixed_history_seeded'] = seeded
            save(out)
        start = time.monotonic(); previous = None; n = 0
        for window, planned in schedule(duration):
            time.sleep(max(0, start+planned-time.monotonic()))
            if window != previous:
                receipt = writer.append(**candidate(0,0,live=window,gap=True))
                send(js,dict(op='select',window=window,id=receipt['event_id']))
                if get_message(js) != 'armed': raise ValueError('browser did not arm')
                previous, n = window, 1
            cycle = dict(window=window,planned_s=planned,start_s=round(time.monotonic()-start,3))
            for mode in ['connected','replay']:
                send(js,{'op':mode})
                if get_message(js) != 'armed': raise ValueError('browser did not arm')
                t = time.monotonic()
                receipt = writer.append(**candidate(0,n,live=window))
                if receipt['duplicated']: raise ValueError('duplicate append')
                n += 1
                send(js,receipt['event_id'])
                reply = get_message(js)
                if reply != 'http': raise ValueError('browser HTTP result missing')
                http_ms = ms(t)
                if get_message(js) != 'visible': raise ValueError('browser visibility check failed')
                visible_ms = ms(t)
                ack = get_message(js)
                if ack['id'] != receipt['event_id'] or ack['count'] != n:
                    raise ValueError('incorrect visible receipt')
                cycle[mode] = dict(**ack,http_body_ms=http_ms,browser_visible_ms=visible_ms)
            cycle.update(reader_kib=rss(reader.pid),node_kib=rss(js.pid),t_s=round(time.monotonic()-start,3))
            out['cycles'].append(cycle)
            if len(out['windows']) == window: out['windows'].append({})
            group = [c for c in out['cycles'] if c['window']==window]
            out['windows'][window] = dict(cycles=len(group),reader_rss_median_kib=statistics.median(c['reader_kib']['VmRSS'] for c in group),
                node_rss_median_kib=statistics.median(c['node_kib']['VmRSS'] for c in group),
                chromium_pss_median_kib=statistics.median(c['replay']['chromium_pss_kib'] for c in group))
            out['elapsed_s'] = round(time.monotonic()-start,3); save(out)
        time.sleep(max(0, start+duration-time.monotonic()))
        out['elapsed_s'] = round(time.monotonic()-start,3)
        for mode in ['connected','replay']:
            out['p95_'+mode] = {k:p95([c[mode][k] for c in out['cycles']]) for k in ['http_body_ms','browser_visible_ms']}
        send(js,{'op':'close'})
        if js.wait(15): raise RuntimeError('browser fixture failed')
        return out


def revisions():
    result = {}
    for name in ['workflow','bundlebees','hyvv','orbitdesktop']:
        def git(*args): return subprocess.check_output(['git','-C',str(ROOT/name),*args],text=True).strip()
        if git('rev-parse','--abbrev-ref','HEAD') != 'HEAD' or git('status','--porcelain'):
            raise RuntimeError(f'{name} must be a clean detached worktree')
        result[name] = git('rev-parse','HEAD')
    return result


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--events',type=int,default=100000,choices=range(5000,100001,5000),metavar='5000..100000 (multiple of 5000)')
    p.add_argument('--samples',type=int,default=100,choices=range(1,101),metavar='1..100')
    p.add_argument('--soak-seconds',type=int,default=1800,choices=range(0,14401),metavar='0..14400')
    p.add_argument('--fixed-history',action='store_true',help='pre-seed the live viewport to the renderer cap (Arm B)')
    p.add_argument('--node-modules',type=Path,help='existing offline Orbit node_modules (esbuild + playwright-core)')
    arms = p.add_mutually_exclusive_group()
    arms.add_argument('--attempt-index', action='store_true', help='deprecated: the default; new ledgers create the index')
    arms.add_argument('--no-attempt-index', action='store_true', help='drop the index before seeding (unindexed control)')
    arms.add_argument('--migrate-attempt-index', action='store_true', help='drop the index, seed, then install it')
    p.add_argument('--chromium',type=Path,help='existing offline Chromium executable')
    p.add_argument('--temp-parent',type=Path,default=Path('/var/tmp'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tuple',type=Path,help='verify the four full commit IDs against this external JSON object')
    return p


def check_fixed_history(p, args):
    if args.fixed_history and args.soak_seconds == 0:
        p.error('--fixed-history requires a positive --soak-seconds')
    return None


def main():
    p = build_parser()
    args = p.parse_args()
    check_fixed_history(p, args)
    if not sys.platform.startswith('linux') or not args.temp_parent.is_dir(): p.error('requires local Linux temp volume')
    if args.soak_seconds:
        if not args.chromium or not os.access(args.chromium,os.X_OK) or not args.node_modules or not (args.node_modules/'playwright-core/index.mjs').is_file():
            p.error('supply offline --chromium and --node-modules for browser runs')
        args.chromium, args.node_modules = args.chromium.resolve(), args.node_modules.resolve()
    if shutil.disk_usage(args.temp_parent).free < 128*1024**2 + 8704*args.events: p.error('insufficient free space')
    if args.output.exists() or args.output.with_suffix(args.output.suffix+'.tmp').exists(): p.error('choose a fresh report path')
    pins = revisions()
    if args.tuple and json.loads(args.tuple.read_bytes()) != pins: p.error('detached revisions differ from expected tuple')
    get = lambda *cmd: subprocess.check_output(cmd,text=True).strip()
    doc = dict(schema='rails-offline-bench/2',status='running',started_utc=utc(),tuple=pins,
               hardware=dict(kernel=platform.release(),machine=platform.machine(),cpu=next(s.split(':')[-1].strip() for s in
                    Path('/proc/cpuinfo').read_text().splitlines() if s.startswith(('model name','Hardware'))),
                    affinity_cpus=len(os.sched_getaffinity(0)),ram_bytes=os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE'),
                    filesystem=get('findmnt','-no','SOURCE,FSTYPE','-T',str(args.temp_parent)),physical_backing='unknown'),
               python=platform.python_version(),sqlite=sqlite3.sqlite_version,
                config=dict(events=args.events,samples_per_surface=args.samples,soak_seconds=args.soak_seconds,lanes=LANES,
                           attempt_index=(index_mode(args) != 'none'),index_mode=index_mode(args),
                           fixed_history=args.fixed_history,
                           logical_rows=PAGE,wire_bytes=query.MAX_BYTES,warmups_per_surface=LANES,p95='nearest rank'))
    def update(key,value): doc[key]=value; snapshot(args.output,doc)
    snapshot(args.output,doc)
    try:
        with tempfile.TemporaryDirectory(dir=args.temp_parent.resolve(),prefix='rails-offline-bench-') as tmp:
            path = Path(tmp)/'synthetic.sqlite'
            blocks, stats = seed(path,args.events,index_mode=index_mode(args)); update('seed',stats)
            data, overview = reads(path,args.samples,blocks,lambda d:update('reads',d)); update('reads',data)
            if args.soak_seconds:
                update('stream',soak(path,args.soak_seconds,overview,args,lambda d:update('stream',d)))
            else: update('stream',{'status':'skipped_by_flag'})
            doc['status']='completed'
    except BaseException as exc:
        doc['status']='failed:'+type(exc).__name__; raise
    finally:
        doc['finished_utc']=utc(); snapshot(args.output,doc)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--reader']:
        from rails_server.http import make_server
        with make_server('127.0.0.1',0,Path(sys.argv[2]),Path(sys.argv[3])) as service:
            print(service.server_port,flush=True); service.serve_forever()
    else: main()
