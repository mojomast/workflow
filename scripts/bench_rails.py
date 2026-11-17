#!/usr/bin/env python3
"""Offline Linux Rails read/stream benchmark. Requires sibling BundleBees and Orbit checkouts.

python3 scripts/bench_rails.py --temp-parent /var/tmp --soak-seconds 1800 --output result.json
Only the report survives. No fixture download, existing DB path, service config or credentials.
"""
import argparse
import hashlib
import http.client
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
BB = ROOT / 'bundlebees' / 'contrib'
ORBIT = ROOT / 'orbitdesktop' / 'contrib'
sys.path.insert(0, str(BB))
from rizzstack_rails import RailsLedger, query  # shared canonical read path, including in HTTP child


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def cpu_info():
    return next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith(('model name', 'Hardware')))


def rss(pid=None):
    fields = Path(f'/proc/{pid or "self"}/status').read_text().splitlines()
    return {name: int(next(line.split()[1] for line in fields if line.startswith(name + ':')))
            for name in ('VmRSS', 'VmHWM')}


def percentile(values, q):
    return sorted(values)[math.ceil(len(values) * q) - 1] if values else None


def milliseconds(start):
    return round((time.perf_counter() - start) * 1000, 3)


def snapshot(path, doc):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(doc, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def tool_args(i, *, live=False):
    slot = i % 10
    key = ('probe' if live else 'row') + str(i)
    scope = {'campaign_id': 'stream' if live else 'campaign', 'job_id': 'stream' if live else 'job',
             'attempt_id': f'probe-{i}' if live else f'attempt-{slot}'}
    return dict(kind='tool.finish', source=dict(adapter='bench', instance='guest', record_id=key, revision='v1'),
                lane={'lane_id': f'lane-{slot}'}, scope=scope, authority='worker_report', dedupe_key=key,
                payload={'call_id': key, 'tool_name': 'shell', 'command_family': 'git', 'outcome': 'ok',
                         'summary': 'completed', 'evidence_ref': None},
                duration_ms=i % 3000, timing_quality='measured')


def seed(path, count):
    # One canonical writer; 10 interleaved active lanes. Batching only amortizes
    # fixture fsync. All records pass the runtime's locked append and hash path.
    db = RailsLedger(path)
    try:
        for start in range(0, count, 200):
            def batch(conn):
                for i in range(start, min(start + 200, count)):
                    db._append_locked(conn, **tool_args(i), occurred_at=None, redaction_policy=None)
            db._write_tx(batch)
        if db.head()['seq'] != count:
            raise RuntimeError('incomplete dataset')
    finally:
        db.close()


def read_bench(path, samples, save):
    db = RailsLedger(path, read_only=True)
    try:
        info = {k: db.query('PRAGMA ' + k)[0][k] for k in ('page_size','cache_size','journal_mode','query_only')}
        out = {'pragmas': info, 'rss_start_kib': rss(), 'series': {}}
        for name, call in [('events', query.query_events), ('view', query.query_view_page)]:
            series = out['series'][name] = {'samples_ms': [], 'row_counts': [], 'wire_bytes': []}
            # Ten interleaved attempt selectors, cursor advances for five visits
            # and then resets to exercise both first and continuation pages.
            cursors = [None] * 10
            for i in range(-10, samples):
                lane = i % 10
                after = cursors[lane] if i >= 0 and i // 10 % 5 else None
                req = query.make_request('attempt', f'attempt-{lane}', format='json', limit=500, after=after)
                start = time.perf_counter()
                result = call(req, db)
                wire = query.wire_json(result).encode('ascii')
                elapsed = milliseconds(start)
                if i >= 0:
                    cursors[lane] = result['next_cursor']
                    n = (len(result['items']) if name == 'events' else
                         sum(len(l['marks']) for l in result['items'][0]['lanes']))
                    if not n or len(wire) > req['max_bytes']:
                        raise AssertionError('invalid bounded projection')
                    series['samples_ms'].append(elapsed)
                    series['row_counts'].append(n)
                    series['wire_bytes'].append(len(wire))
                if i == 0 or i % 10 == 9:
                    save(out)
            series['p95_ms'] = percentile(series['samples_ms'], .95)
            series['rss_end_kib'] = rss()
            save(out)
        return out
    finally:
        db.close()


def serve(path, cred, channel):
    sys.path.insert(0, str(ORBIT))
    from rails_server.http import make_server
    svc = make_server('127.0.0.1', 0, path, cred)
    channel.send(svc.server_port)
    channel.close()
    try:
        svc.serve_forever()
    finally:
        svc.server_close()


def frame(resp, expected):
    fields = {}
    for _ in range(10):
        line = resp.readline(1024)
        if not line:
            break
        if line == b'\n' and fields.get('event') == expected:
            return fields['id']
        if b': ' in line:
            k, v = line.decode('ascii').rstrip().split(': ', 1)
            fields[k] = v
    raise AssertionError('missing SSE ' + expected)


def stream_bench(path, duration, save):
    # Dedicated real loopback HTTP server subprocess. Never use an existing port,
    # service or secrets. RSS below belongs to the server alone (not the seeder/client).
    token = secrets.token_urlsafe(32)
    cred = path.parent / 'read-token'
    cred.touch(mode=0o600)
    cred.write_text(token)
    ctx = mp.get_context('spawn')
    rx, tx = ctx.Pipe(False)
    proc = ctx.Process(target=serve, args=(path, cred, tx), daemon=True)
    writer = RailsLedger(path)
    proc.start()
    tx.close()
    try:
        if not rx.poll(20):
            raise RuntimeError('offline service did not start')
        port = rx.recv()
        hdr = {'Authorization': 'Bearer ' + token}
        sse_path = '/v1/stream?kind=job&id=stream'

        def connect(last):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            conn.request('GET', sse_path, headers={**hdr, **({'Last-Event-ID':last} if last else {})})
            resp = conn.getresponse()
            if resp.status != 200:
                raise RuntimeError(f'bench stream HTTP {resp.status}')
            return conn, resp, frame(resp, 'ready')

        def read_mark(i, event_id):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                # The harness knows its exact event ID; SSE sends an invalidation, not a mark.
                conn.request('GET', '/v1/view?kind=event&id=' + event_id, headers=hdr)
                resp = conn.getresponse()
                obj = json.loads(resp.read(131073))
                if resp.status != 200 or [m['event_id'] for l in obj['lanes'] for m in l['marks']] != [event_id]:
                    raise AssertionError(f'HTTP view missing probe {i}: {resp.status}')
            finally:
                conn.close()

        start = time.monotonic()
        out = {'started_utc': utc(), 'requested_s': duration, 'server_rss_start_kib': rss(proc.pid), 'windows': []}
        last = None
        while time.monotonic() - start < duration:
            i = 2 * len(out['windows'])
            conn, resp, ready = connect(last)
            try:
                if last is not None and last != ready:
                    raise AssertionError('resume position changed')
                t = time.perf_counter()
                target = writer.append(**tool_args(i, live=True))['event_id']
                last = frame(resp, 'invalidate')
                transport = milliseconds(t)
                read_mark(i, target)
                mark = milliseconds(t)
            finally:
                resp.close()
                conn.close()
            # Commit offline, reconnect with the last *consumed* ID, check content.
            target = writer.append(**tool_args(i+1, live=True))['event_id']
            t = time.perf_counter()
            conn, resp, ready = connect(last)
            try:
                if ready != last:
                    raise AssertionError('reconnected at wrong cursor')
                advanced = frame(resp, 'invalidate')
                if advanced == last:
                    raise AssertionError('cursor failed to advance')
                last = advanced
                read_mark(i+1, target)
                replay = milliseconds(t)
            finally:
                resp.close()
                conn.close()
            out['windows'].append(dict(t_s=round(time.monotonic()-start, 3), notify_ms=transport,
                                       mark_ms=mark, resume_mark_ms=replay, **rss(proc.pid)))
            out['elapsed_s'] = round(time.monotonic() - start, 3)
            save(out)
            time.sleep(max(0, min(10, duration - (time.monotonic() - start))))
        out['elapsed_s'] = round(time.monotonic() - start, 3)
        for field in ('notify_ms', 'mark_ms', 'resume_mark_ms'):
            out['p95_' + field] = percentile([w[field] for w in out['windows']], .95)
        return out
    finally:
        rx.close()
        proc.terminate()
        proc.join(10)
        writer.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--events', type=int, default=100000, choices=range(1000,100001), metavar='1000..100000')
    p.add_argument('--samples', type=int, default=100, choices=range(1,201), metavar='1..200')
    p.add_argument('--soak-seconds', type=int, default=1800, choices=range(0,1801), metavar='0..1800')
    p.add_argument('--temp-parent', type=Path, default=Path('/var/tmp'))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if sys.platform != 'linux' or not args.temp_parent.is_dir():
        p.error('requires Linux and a local temporary parent directory')
    if shutil.disk_usage(args.temp_parent).free < 128 * 1024**2 + 8704 * args.events:
        p.error('insufficient free space for requested fixture')
    if args.output.exists() or args.output.with_suffix(args.output.suffix + '.tmp').exists():
        p.error('choose a fresh report path')
    doc = {'schema':'rails-offline-bench/1', 'started_utc':utc(), 'status':'running',
           'hardware':{'kernel':platform.release(), 'architecture':platform.machine(), 'cpu':cpu_info(),
                       'visible_cpus':os.cpu_count(), 'affinity_cpus':len(os.sched_getaffinity(0)),
                       'ram_bytes':os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE'),
                       'filesystem':subprocess.check_output(['findmnt','-no','SOURCE,FSTYPE','-T',str(args.temp_parent)],text=True).strip()},
           'python':platform.python_version(), 'sqlite':sqlite3.sqlite_version,
           'code_sha256': {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in [Path(__file__).resolve(), *(BB/'rizzstack_rails').glob('*.py'),
                                         ORBIT/'rails_server'/'http.py', ORBIT/'rails_server'/'stream.py']},
           'config':{'events':args.events, 'samples_per_surface':args.samples, 'lane_count':10,
                     'soak_seconds':args.soak_seconds, 'page_limit':500, 'wire_cap_bytes':32768,
                     'warmups_per_surface':10, 'p95':'nearest rank'}}
    def update(section, data):
        doc[section] = data
        snapshot(args.output, doc)
    snapshot(args.output, doc)
    with tempfile.TemporaryDirectory(dir=args.temp_parent, prefix='rails-offline-bench-') as tmp:
        path = Path(tmp) / 'synthetic.sqlite'
        try:
            start = time.perf_counter()
            # Isolate dataset construction RSS from reader measurements.
            proc = mp.get_context('spawn').Process(target=seed, args=(path,args.events))
            proc.start()
            proc.join()
            if proc.exitcode != 0:
                raise RuntimeError('fixture builder failed')
            update('seed', {'elapsed_ms':milliseconds(start), 'db_bytes':path.stat().st_size})
            update('reads', read_bench(path, args.samples, lambda data: update('reads',data)))
            if args.soak_seconds:
                update('stream', stream_bench(path, args.soak_seconds, lambda data: update('stream',data)))
            else:
                update('stream', {'status':'skipped_by_flag'})
            doc['status'] = 'completed'
        except BaseException as exc:
            doc['status'] = 'failed:' + type(exc).__name__
            raise
        finally:
            doc['finished_utc'] = utc()
            snapshot(args.output, doc)


if __name__ == '__main__':
    main()
