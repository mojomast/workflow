"""R18 local acceptance. See specs/rails-rollout.md for prerequisites and scope."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from urllib.parse import urlencode

from tests.test_rails_contract import canonical, load_json, rails_hash, validate_schema


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'schemas' / 'rails'
SCENARIO = SCHEMAS / 'fixtures' / 'm1-scenario.json'
SIBLINGS = Path(os.environ.get('RAILS_R18_ROOT', ROOT.parent)).resolve()
HYVV, BB, ORBIT = (SIBLINGS / repo for repo in ('hyvv', 'bundlebees', 'orbitdesktop'))
LOCAL = '127.0.0.1'


def verify_origin(events, anchor):
    """Receiver check: recompute from genesis, compare to an independently read head."""
    previous = 'genesis'
    for seq, row in enumerate(events, 1):
        body = {k: v for k, v in row.items() if k != 'hash'}
        if (row['chain_id'] != anchor['chain_id'] or row['seq'] != seq or
                row['event_id'] != f"{anchor['chain_id']}:{seq}" or
                row['prev_hash'] != previous or rails_hash(previous, body) != row['hash']):
            raise ValueError('invalid origin range')
        previous = row['hash']
    if len(events) != anchor['seq'] or previous != anchor['hash']:
        raise ValueError('wrong anchored head')


def check_sidecar(doc, events, worker_head, local_head, checkpoint, selection, revision, contract):
    errors = validate_schema(doc, load_json(SCHEMAS / 'evidence.schema.json'))
    if errors:
        raise ValueError('; '.join(errors))
    if doc['origin_heads'] != [worker_head, local_head] or doc['imported_checkpoints'] != [checkpoint]:
        raise ValueError('wrong evidence head or checkpoint')
    verify_origin(events, worker_head)
    if {k: checkpoint[k] for k in worker_head} != worker_head:
        raise ValueError('peer checkpoint does not anchor the complete exported range')
    if doc['code_rev'] != revision or doc['contract_sha256'] != contract:
        raise ValueError('wrong code or contract revision')
    if doc['selected_event_ids'] != selection:
        raise ValueError('wrong selected events')
    if doc['verification_links']:
        raise ValueError('fixture run produced no independent verification record')


class Scenario(unittest.TestCase):
    def test_packet_and_wrong_head(self):
        scenario = load_json(SCENARIO)
        self.assertEqual(scenario['scope'], 'local synthetic launcher trace')
        self.assertEqual(scenario['receiver_decision'], 'pending')
        self.assertEqual(scenario['query']['selector']['id'], scenario['attempt_id'])
        request_schema = next(x for x in load_json(SCHEMAS / 'query.schema.json')['anyOf']
                              if x['properties']['schema']['const'] == 'rizzstack.rails-query/1')
        self.assertEqual(validate_schema(scenario['query'], request_schema), [])
        vectors = load_json(SCHEMAS / 'fixtures' / 'hash-vectors.json')['origin_chain']
        rows = [dict(row, hash=digest) for row, digest in zip(vectors['envelopes'], vectors['expected_hashes'])]
        head = {k: rows[-1][k] for k in ('chain_id', 'seq', 'hash')}
        verify_origin(rows, head)
        for wrong in (rows[:-1], list(reversed(rows)), [dict(rows[0], authority='owner_record'), *rows[1:]]):
            with self.assertRaises(ValueError):
                verify_origin(wrong, head)


def require(path):
    if not path.exists():
        reason = f'missing local prerequisite: {path.parent.name}/{path.name}'
        if os.environ.get('RAILS_R18_REQUIRED') == '1':
            raise AssertionError(reason)
        raise unittest.SkipTest(reason)


def require_browser():
    if not os.environ.get('RAILS_R18_BROWSER_DIST'):
        reason = 'browser not exercised: set RAILS_R18_BROWSER_DIST to a local build from the tested source'
        if os.environ.get('RAILS_R18_REQUIRED') == '1':
            raise AssertionError(reason)
        raise unittest.SkipTest(reason)


def free_port():
    with socket.socket() as sock:
        sock.bind((LOCAL, 0))
        return sock.getsockname()[1]


def request(port, path, token=None, *, origin=False, method='GET'):
    headers = {'Origin': f'http://{LOCAL}:{port}'} if origin else {}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    with contextlib.closing(http.client.HTTPConnection(LOCAL, port, timeout=3)) as conn:
        conn.request(method, path, headers=headers)
        reply = conn.getresponse()
        data = reply.read(131073)
        if len(data) > 131072:
            raise ValueError('oversize HTTP result')
        return reply.status, data


def json_ok(port, path, token, **kw):
    status, raw = request(port, path, token, **kw)
    if status != 200:
        raise AssertionError(f'{path.split("?")[0]}: HTTP {status}')
    return json.loads(raw)


@contextlib.contextmanager
def serving(args, cwd, env, port, ready_path):
    with tempfile.TemporaryFile() as logs:
        proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=logs, stderr=logs)
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError(f'{ready_path}: child exited {proc.returncode} before ready')
                try:
                    status, _ = request(port, ready_path)
                    if status in (200, 401, 403):
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.05)
            else:
                raise AssertionError(f'{ready_path}: readiness timeout')
            yield
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=4)


def isolated_env(root):
    # No inherited credentials, profiles, HTTP proxies or PYTHONPATH.
    home = root / 'home'
    home.mkdir(exist_ok=True)
    return {'PATH': os.environ['PATH'], 'HOME': str(home), 'USERPROFILE': str(home),
            'TMPDIR': str(root), 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'ORBIT_AGENT_DISCOVERY': 'off'}


def secret_file(path):
    value = secrets.token_urlsafe(36)
    with path.open('x') as handle:
        path.chmod(0o600)
        handle.write(value)
    return value


def import_page(db, chain, port, credential, env, *, replay=False):
    """One short-lived coordinator process per pull. No in-memory cursor survives."""
    code = '''
import json, sys
from contextlib import closing
from pathlib import Path
from bundlebees_plugin.rails_remote_source import RemoteRailSource, PeerUnavailable
from rizzstack_rails import RailsLedger
db, chain, port, key, replay = sys.argv[1:]
peer = RemoteRailSource('http://127.0.0.1:'+port, peer_id='worker-1', env={}, timeout=2,
                        token_provider=lambda: Path(key).read_text().strip())
with closing(RailsLedger(db)) as writer:
    try:
        report = peer.import_into(writer, chain, cursor=0 if replay=='1' else None, limit=32)
        print(json.dumps(report['ledger']))
    except PeerUnavailable:
        print(json.dumps({'unavailable': True}))
'''
    proc = subprocess.run([sys.executable, '-c', code, str(db), chain, str(port), str(credential),
                           str(int(replay))], env=env, cwd=BB, capture_output=True, timeout=8, check=True)
    return json.loads(proc.stdout)


class LocalSlice(unittest.TestCase):
    def setUp(self):
        require(BB / 'bundlebees_plugin/rails_remote_source.py')
        require(BB / 'contrib/rizzstack_rails/feedback.py')
        tmp = tempfile.TemporaryDirectory(prefix='r18-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / 'coordinator.sqlite'
        self.env = isolated_env(self.root)
        self.case = load_json(SCENARIO)
        self.aid = self.case['attempt_id']
        # The read assertions use BundleBees. hyvv and Orbit load their own
        # installed/vendor copies in separate processes with no shared sys.path.
        sys.path.insert(0, str(BB / 'contrib'))
        self.addCleanup(sys.path.remove, str(BB / 'contrib'))
        from rizzstack_rails import RailsLedger
        self.open_ledger = RailsLedger

    def worker(self):
        require(HYVV / 'rails_export.py')
        require(HYVV / 'contrib/rizzstack_rails/ledger.py')
        root = self.root / 'worker'
        journal = root / 'attempts' / (self.aid + '.events.jsonl')
        journal.parent.mkdir(parents=True)
        self.peer_file = root / 'reader'
        reader = secret_file(self.peer_file)
        secret_file(root / 'orbit-api.token')
        port = free_port()
        config = root / 'config.json'
        config.write_text(json.dumps(dict(data_dir=str(root), bind=LOCAL, extra_binds=[], port=port,
                                          rails_enabled=True, rails_read_token_file=str(self.peer_file),
                                          rails_read_peers=[LOCAL])))
        def start():
            # No execution submitted. The built-in idle test backend avoids Cua
            # startup; the actual launcher serves and backfills the journal.
            return serving([sys.executable, 'launcher.py', 'serve', '--config', str(config), '--backend', 'fake'],
                           HYVV, self.env, port, '/v1/rails/head')
        return journal, port, reader, start

    def collect(self):
        journal, port, reader, start = self.worker()
        rows = self.case['journal']
        journal.write_bytes(canonical(rows[0]) + b'\n')
        with start():
            self.assertEqual(request(port, '/v1/rails/events')[0], 401)
            first = json_ok(port, '/v1/rails/events?after=0&limit=32', reader)
            chain = first['chain_id']
            self.assertEqual([e['kind'] for e in first['events'] if e['kind'].startswith('tool.')], ['tool.start'])
            one = import_page(self.db, chain, port, self.peer_file, self.env)
            self.assertEqual(one['imported'], first['head']['seq'])
        self.assertEqual(import_page(self.db, chain, port, self.peer_file, self.env), {'unavailable': True})
        with contextlib.closing(self.open_ledger(self.db, read_only=True)) as db:
            self.assertEqual(db.import_cursor(chain)['head_hash'], first['head']['hash'])
        with journal.open('ab') as handle:
            for row in rows[1:]:
                handle.write(canonical(row) + b'\n')
        with start():
            status, raw = request(port, '/v1/rails/events?after=0&limit=32', reader)
            self.assertEqual(status, 200)
            self.assertNotIn(b'r18-private-canary', raw)
            page = json.loads(raw)
            self.assertFalse(page['has_more'])
            self.assertEqual(first['events'], page['events'][:len(first['events'])])
            self.assertEqual(chain, page['chain_id'])
            self.events = page['events']
            for event in self.events:
                self.assertIn(canonical(event), raw)
                self.assertEqual(event['authority'], 'worker_report')
            exported = json_ok(port, '/v1/rails/head', reader)
            self.head = dict(chain_id=chain, **page['head'])
            self.assertEqual(exported['chain_id'], chain)
            self.assertEqual(exported['head'], page['head'])
            verify_origin(self.events, self.head)
            tools = [e for e in self.events if e['kind'].startswith('tool.')]
            self.assertEqual([e['kind'] for e in tools], self.case['expected_tool_kinds'])
            self.assertEqual(tools[0]['payload']['call_id'], tools[1]['payload']['call_id'])
            self.assertTrue(all(e['duration_ms'] is None for e in tools))
            self.tool_ids = [e['event_id'] for e in tools]
            two = import_page(self.db, chain, port, self.peer_file, self.env)
            self.assertEqual(two['imported'], len(self.events) - one['imported'])
            duplicate = import_page(self.db, chain, port, self.peer_file, self.env, replay=True)
            self.assertEqual(duplicate['imported'], 0)
        with contextlib.closing(self.open_ledger(self.db, read_only=True)) as db:
            stored = db.query('SELECT origin_bytes FROM imported_origin_rows WHERE chain_id=? ORDER BY seq', (chain,))
            self.assertEqual([r['origin_bytes'] for r in stored], [canonical(e).decode() for e in self.events])
            receipts = db.query('SELECT through_seq,head_hash FROM import_receipts WHERE chain_id=? ORDER BY through_seq', (chain,))
            self.assertEqual([r['through_seq'] for r in receipts], [one['through_seq'], two['through_seq']])
            last = receipts[-1]
            self.checkpoint = dict(chain_id=chain, seq=last['through_seq'], hash=last['head_hash'], source='rails_remote')
            self.assertTrue(db.verify_chain(chain)['ok'])

    def feedback(self):
        from rizzstack_rails import feedback
        args = dict(self.case['feedback'], scope={'attempt_id': self.aid})
        target = self.tool_ids[-1]
        with contextlib.closing(self.open_ledger(self.db)) as db:
            first = feedback.record(db, target, **args)
        with contextlib.closing(self.open_ledger(self.db)) as db:
            second = feedback.record(db, target, **args)
            self.assertTrue(second['duplicated'])
            self.assertEqual(first['event_id'], second['event_id'])
            self.assertEqual([r['event_id'] for r in feedback.history(db, target_event_id=target)], [first['event_id']])
            self.assertEqual(feedback.distinct_interventions(db), 0)
        return first['event_id']

    def test_import_restart_and_local_feedback(self):
        self.collect()
        self.feedback()

    def test_registered_proxy_cli_and_return(self):
        self.registered_read(check_browser=False)

    def test_browser_inspector_and_cli_identity(self):
        require_browser()
        self.registered_read(check_browser=True)

    def test_offline_coding_campaign(self):
        require(BB / 'bundlebees_plugin/rails_bundlebees_source.py')
        require_browser()
        require(BB / 'bundlebees_plugin/rails_return.py')
        sys.path.insert(0, str(BB))
        self.addCleanup(sys.path.remove, str(BB))
        with patch.dict(os.environ, {**self.env, **{k: os.environ[k] for k in
                ('RAILS_R18_REQUIRED', 'RAILS_R18_BROWSER_DIST', 'RAILS_R18_CAMPAIGN_DIR', 'RAILS_R18_RECEIVER_CAPTURE',
                 'CHROMIUM_EXECUTABLE', 'PLAYWRIGHT_BROWSERS_PATH') if k in os.environ},
                'WORKFLOW_SRC': str(ROOT), 'GIT_CONFIG_NOSYSTEM': '1',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}, clear=True):
            self.registered_read(check_browser=True, campaign=True)

    def registered_read(self, *, check_browser, campaign=False):
        require(BB / 'bundlebees_plugin/rails_cli.py')
        require(ORBIT / 'contrib/rails_server/__main__.py')
        require(ORBIT / 'contrib/rizzstack_rails/query.py')
        require(ORBIT / 'server/rails-proxy.mjs')
        require(ORBIT / 'node_modules/ws')
        node = shutil.which('node')
        if not node or not self.node_supported(node):
            reason = 'Orbit requires local Node >=22.12 with its installed native dependencies'
            if os.environ.get('RAILS_R18_REQUIRED') == '1':
                self.fail(reason)
            self.skipTest(reason)
        if campaign:
            self.campaign_setup()
        self.collect()
        if campaign:
            self.campaign_finish()
        feedback_id = self.feedback()
        token_file = self.root / 'service-reader'
        read_token = secret_file(token_file)
        owner = secrets.token_urlsafe(36)
        port = free_port()
        server_env = dict(self.env, ORBIT_RAILS_PORT=str(port), ORBIT_RAILS_READ_TOKEN_FILE=str(token_file),
                          RIZZSTACK_RAILS_DB=str(self.db))
        backend = [sys.executable, '-m', 'contrib.rails_server']
        with serving(backend, ORBIT, server_env, port, '/v1/health'):
            self.assertEqual(request(port, '/v1/health')[0], 401)
            self.assertEqual(request(port, '/v1/feedback', read_token, method='POST')[0], 403)
            orbit_port = free_port()
            orbit_env = dict(server_env, ORBIT_TOKEN=owner, ORBIT_HOST=LOCAL, PORT=str(orbit_port),
                             ORBIT_RUNTIME_DIR=str(self.root / 'orbit'), ORBIT_CWD=str(self.root),
                             ORBIT_TMUX_SOCKET='r18-' + secrets.token_hex(6), ORBIT_TMUX_CONFIG=os.devnull)
            orbit_root = ORBIT
            dist = os.environ.get('RAILS_R18_BROWSER_DIST') if check_browser else None
            if dist:
                # Never replace a checkout's dist or attach to an existing browser/server.
                dist = Path(dist).resolve(strict=True)
                self.assertTrue((dist / 'index.html').is_file())
                orbit_root = self.root / 'orbit-source'
                shutil.copytree(ORBIT / 'server', orbit_root / 'server')
                for name in ('src', 'apps', 'scripts', 'contracts', 'docs', 'public', 'packages', 'node_modules', 'package.json'):
                    (orbit_root / name).symlink_to(ORBIT / name)
                (orbit_root / 'dist').symlink_to(dist, target_is_directory=True)
            with serving([node, '--experimental-strip-types', 'server/index.mjs'], orbit_root, orbit_env,
                         orbit_port, '/api/health'):
                self.assertEqual(json_ok(orbit_port, '/api/health', None)['service'], 'orbit')
                prefix = '/api/rizzstack/rails/'
                self.assertEqual(request(orbit_port, prefix + 'health', None, origin=True)[0], 401)
                self.assertEqual(request(orbit_port, prefix + 'health', read_token, origin=True)[0], 403)
                # Reader-only deployment: neither a successful vote nor a queued retry can come from here.
                for route in ('feedback', 'interventions'):
                    status, body = request(orbit_port, prefix + route, owner, origin=True, method='POST')
                    self.assertEqual((status, json.loads(body)['error']['code']), (503, 'capability_unavailable'))
                q = self.case['query']
                params = urlencode({**q['selector'], 'format': q['format'], 'limit': q['limit'],
                                    'max_bytes': q['max_bytes'], 'include': ','.join(q['include']),
                                    'show_tokens': 'false'})
                with contextlib.closing(self.open_ledger(self.db, read_only=True)):
                    snapshot = self.db_fingerprint()
                    result = json_ok(orbit_port, prefix + 'events?' + params, owner, origin=True)
                    view = json_ok(orbit_port, prefix + 'view?' + params, owner, origin=True)
                    cli = subprocess.run([sys.executable, '-m', 'bundlebees_plugin.rails_cli', 'query',
                                          '--kind', q['selector']['kind'], '--id', self.aid,
                                          '--format', q['format'], '--limit', str(q['limit']),
                                          '--max-bytes', str(q['max_bytes']), '--include', ','.join(q['include'])], cwd=BB, env=server_env,
                                         check=True, capture_output=True, timeout=8)
                    self.assertEqual(self.db_fingerprint(), snapshot)
                self.assertEqual(result, json.loads(cli.stdout))
                self.assertEqual(result['schema'], 'rizzstack.rails-result/1')
                self.assertTrue(result['ok'])
                self.assertFalse(result['has_more'] or result['truncated'])
                self.assertEqual(validate_schema(view, load_json(SCHEMAS / 'view.schema.json')), [])
                ids = [row['event_id'] for row in result['items']]
                marks = [m['event_id'] for lane in view['lanes'] for m in lane['marks']]
                for event_id in [*self.tool_ids, feedback_id]:
                    self.assertEqual(ids.count(event_id), 1)
                    self.assertEqual(marks.count(event_id), 1)
                vote, = [r for r in result['items'] if r['event_id'] == feedback_id]
                self.assertEqual((vote['rating'], vote['category'], vote['target_event_id']), (1, 'quality', self.tool_ids[-1]))
                self.assertNotIn('r18-private-canary', json.dumps([view, result]))
                if dist:
                    selected = self.campaign_checks(orbit_port, owner, server_env) if campaign else self.tool_ids[-1]
                    self.browser_selection = self.inspect_mark(node, orbit_port, owner, selected, campaign)
                    self.assertEqual(self.browser_selection['selected_event_id'], selected)
                    self.browser_selection['dist_index_sha256'] = hashlib.sha256((dist / 'index.html').read_bytes()).hexdigest()
        if campaign:
            self.campaign_handoff(feedback_id)
        else:
            self.write_return(feedback_id, result, view, keep=check_browser or not os.environ.get('RAILS_R18_BROWSER_DIST'))

    def inspect_mark(self, node, port, owner, selected, by_event=False):
        """Connect through the real shell; click the exact imported mark in its opaque renderer."""
        js = '''
import {chromium} from 'playwright-core';
import {readFileSync} from 'node:fs';
const cfg=JSON.parse(readFileSync(0,'utf8'));
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,
  args:['--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const ctx=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await ctx.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());
  await ctx.addInitScript(()=>{if(window===top)localStorage.setItem('orbit.onboarding.v1','done')});
  const page=await ctx.newPage();page.setDefaultTimeout(10000);
  await page.goto(cfg.origin);
  await page.getByRole('button',{name:'Connect local host',exact:true}).click();
  await page.getByLabel('Host session token').fill(cfg.owner);
  await page.getByRole('button',{name:'Unlock local host',exact:true}).click();
  await page.getByLabel('Host session token').waitFor({state:'hidden'});
  await page.keyboard.press('Control+k');
  const search=page.getByRole('combobox',{name:'Search workspace commands'});
  await search.fill('Rizzstack Rails');await search.press('Enter');
  const dialog=page.getByRole('dialog',{name:'Rizzstack Rails'});
  const renderer=page.frameLocator('iframe[title="Read-only Rails timeline"]');
  const details=[];
  for(const mark of cfg.marks){
    await dialog.getByLabel('Selector kind').selectOption(mark.kind);
    await dialog.getByLabel('Public selector ID').fill(mark.id);
    await dialog.getByRole('button',{name:'Inspect history'}).click();
    await renderer.locator(`.rail-mark[data-event-id="${mark.event}"]`).click();
    const id=await renderer.locator('#rails-inspector').getByText(mark.event,{exact:true}).first().innerText();
    const ack=dialog.locator('p').filter({hasText:'Selected event: '+id}).filter({hasText:'authority: '+mark.authority});
    await ack.waitFor();details.push({event_id:id,owner_detail:await ack.innerText()});
  }
  console.log(JSON.stringify({selected_event_id:details.at(-1).event_id, details, browser_version:browser.version()}));
} finally {await browser.close()}
'''
        browser_env = dict(self.env)
        for name in ('CHROMIUM_EXECUTABLE', 'PLAYWRIGHT_BROWSERS_PATH'):
            if name in os.environ:
                browser_env[name] = os.environ[name]
        # The worker signs no coordinator authority: the reader exposes a transported
        # worker_report as an imported_observation on this read-only deployment.
        marks = [dict(kind='attempt', id=self.aid, event=self.tool_ids[-1], authority='imported_observation')]
        if by_event:
            for phase in ('red', 'integration'):
                eid = self.phases[phase]['event_id']
                marks.append(dict(kind='event', id=eid, event=eid, authority='verifier_record'))
        proc = subprocess.run([node, '--input-type=module', '-e', js], cwd=ORBIT, env=browser_env,
                              input=json.dumps(dict(owner=owner, origin=f'http://{LOCAL}:{port}', marks=marks)),
                              capture_output=True, text=True, timeout=60)
        if proc.returncode:
            # Playwright can include input values in a failing trace. Keep the test credential private.
            self.fail(proc.stderr.replace(owner, '[redacted]')[-2000:])
        observed = json.loads(proc.stdout)
        self.assertEqual([d['event_id'] for d in observed['details']], [m['event'] for m in marks])
        self.assertEqual(observed['selected_event_id'], selected)
        if by_event:
            for detail, revision in zip(observed['details'][1:], (self.base, self.integrated)):
                self.assertIn('code_rev: ' + revision, detail['owner_detail'])
                self.assertIn('contract_sha256: ' + self.contract_hash, detail['owner_detail'])
        return observed

    @staticmethod
    def node_supported(node):
        version = subprocess.check_output([node, '--version'], text=True, timeout=4).strip()
        return tuple(int(n) for n in version.lstrip('v').split('.')[:2]) >= (22, 12)

    def db_fingerprint(self):
        return [(p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in
                (self.db, Path(str(self.db) + '-wal')) if p.exists()]

    def git(self, *argv, cwd=None):
        return subprocess.check_output(['git', *argv], cwd=cwd or self.repo, env=self.env,
                                       text=True, stderr=subprocess.PIPE, timeout=15).strip()

    def phase_check(self, cwd, argv):
        """Only the secret-free, committed fixture is executable. Capture actual per-case results."""
        from bundlebees_plugin import tdd
        self.assertEqual(list(argv[:3]), [sys.executable, '-m', 'pytest'])
        self.assertTrue(Path(cwd).resolve().is_relative_to(self.root))
        junit = self.root / 'last-run.xml'
        junit.unlink(missing_ok=True)
        proc = subprocess.run([*argv, '-p', 'no:cacheprovider', '--junitxml', str(junit)],
                              cwd=cwd, env=dict(self.env, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'),
                              capture_output=True, timeout=30)
        self.assertTrue(junit.is_file(), f'pytest in isolated Python unavailable or failed before collection (exit {proc.returncode})')
        cases = tdd.parse_junit_cases(junit)
        self.assertEqual([c['id'] for c in cases], [self.coding['test_id']])
        totals = {name: sum(c['outcome'] == outcome for c in cases) for name, outcome in
                  [('failures','failed'), ('errors','error'), ('skipped','skipped')]}
        self.assertEqual((totals['errors'], totals['skipped']), (0, 0))
        return dict(exit_code=proc.returncode, timed_out=False, junit=dict(tests=len(cases), **totals),
                    backend='local-synthetic', cases=cases)

    def campaign_setup(self):
        from bundlebees_plugin import acdd_cli, contract, job as jobs, leases, tdd
        self.coding = c = self.case['coding_campaign']
        self.repo, self.state = self.root / 'repo', self.root / 'bb-state'
        self.repo.mkdir(); self.state.mkdir(mode=0o700)
        self.git('init', '-q', '-b', 'baseline')
        self.git('config', 'user.name', 'r18-fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        (self.repo / c['implementation']).write_text(c['baseline'])
        (self.repo / c['test_file']).write_text(c['approved_test'])
        self.git('add', '--', c['implementation'], c['test_file']); self.git('commit', '-qm', 'frozen failing fixture')
        self.base = self.git('rev-parse', 'HEAD')
        self.contract = contract.freeze_contract(dict(contract_version='acdd/1', id='r18-score', title='Empty score',
            outcome=dict(summary='Sum scores', observable_behavior=['score([]) == 0']),
            interfaces=[dict(name='score', kind='function', change='modify')],
            acceptance_criteria=[dict(id=c['criterion'], statement='An empty input scores zero',
                                      verification='test', tests=[c['test_id']])],
            dependencies=[], assumptions=[], scope=dict(assigned_files=[c['implementation']], test_files=[c['test_file']]),
            source_rev=self.base, tdd=dict(applicable=True), verification=dict(independent=True),
            evidence_required=['red','green','integration'], authorization=dict(human_gates=['merge','release','deploy','publish'])),
            approved_by='synthetic-test-intent')
        self.contract_hash = contract.check_frozen(self.contract)
        job_id, task_id = c['job_id'], self.contract['id']
        objective = 'Implement empty score in the offline fixture'
        files, acceptance = [c['implementation']], dict(criteria=[c['criterion']], tests=[c['test_id']])
        # Test admission only. This fixture input is never a real owner's authorization.
        auth = jobs.record_authorization(self.state, job_id=job_id, statement=objective, repo='fixture/r18',
            base_rev=self.base, scope=files, bees=1, wall_clock_s=180, gates=self.contract['authorization']['human_gates'],
            require_tty=False, interactive=False, by='synthetic-test-intent')
        self.packet = dict(packet_version='rizzstack.feature-packet/1', job_id=job_id, feature_id='empty-score',
            workflow_ref=self.git('rev-parse', 'HEAD', cwd=ROOT), repository=dict(identity=auth['repo'], branch='baseline'),
            request=dict(summary=objective, provenance='r18-offline-fixture'), budget=auth['budget'],
            authorization=dict(reference=f'auth:{job_id}', approved_by=auth['by'], approved_at=auth['at']),
            contract=self.contract, contract_sha256=self.contract_hash, source_policy=dict(kind='exact', revision=self.base),
            scope=dict(lease=files, read_only=[c['test_file']]), tests=[c['test_id']], acceptance_ids=[c['criterion']],
            human_gates=auth['gates'], required_evidence=['red','green','regression','integration'],
            prohibited=['push', 'edit approved tests'])
        jobs.create_job(self.state, job_id=job_id, packet=self.packet, tasks=[dict(task_id=task_id, objective=objective,
            lease=files, acceptance=acceptance, contract=self.contract, contract_sha256=self.contract_hash)])
        # Test-only operator assignment. Provision this synthetic dispatch target
        # before collect() even creates a launcher journal. No evidence row or
        # generated head/selection is the source of the assignment.
        target = self.root / 'worker'
        target.mkdir()
        with contextlib.closing(self.open_ledger(target / 'rails.sqlite')) as empty:
            self.assertEqual(empty.head()['seq'], 0)
            assigned_chain = empty.chain_id
        self.lease = leases.record_lease(self.state, self.aid, dict(job_id=job_id, task_id=task_id, objective=objective,
            project=self.packet['repository']['identity'],
            source_rev=self.base, assigned_files=files, contract=self.contract, contract_sha256=self.contract_hash,
            acceptance=acceptance), dispatch_chain_id=assigned_chain)
        self.suite = [sys.executable, '-m', 'pytest', '-q']
        self.key = leases.evidence_key(self.state)
        test_result = self.phase_check(self.repo, self.suite + [c['test_id']])
        self.assertEqual((test_result['exit_code'], test_result['cases'][0]['outcome']), (1, 'failed'))
        self.red = tdd.make_record(self.contract, self.contract_hash, phase='red', revision=self.base,
            test_fingerprints=tdd.fingerprint_files(self.repo, [c['test_file']]), command=['pytest', '-q', c['test_id']],
            result=dict(exit_code=1, timed_out=False, cases=test_result['cases'], **test_result['junit']),
            produced_by=dict(role='verifier',name='fixture-verifier'), test_first=True)
        tdd.check_red(self.contract, self.contract_hash, self.red)
        tdd.write_record(self.state, self.red, self.key)
        self.preflight = acdd_cli.verify_preflight(self.lease, self.state, [c['implementation']])
        self.campaign_import()  # commit baseline RED before the worker range arrives

    def campaign_import(self):
        from bundlebees_plugin.rails_bundlebees_source import BundlebeesSource
        from rizzstack_rails.importer import Importer
        with contextlib.closing(self.open_ledger(self.db)) as writer:
            source = BundlebeesSource.from_existing_state(self.state)
            importer = Importer(writer, authorities=('worker_report','verifier_record','coordinator_record','imported_observation'))
            page = importer.import_once(source)
            self.assertFalse(page['has_more'])
            return page['imported']

    def campaign_finish(self):
        from bundlebees_plugin import acdd_cli, bee_events, cli, integrate_job, job as jobs, tdd, verify_local
        from bundlebees_plugin.rails_outbox_source import RailsOutboxSource
        c = self.coding
        candidate = self.root / 'candidate-tree'
        self.git('worktree', 'add', '--detach', str(candidate), self.base)
        (candidate / c['implementation']).write_text(c['candidate'])
        self.patch_file = self.root / 'candidate.patch'
        self.patch_file.write_bytes(subprocess.check_output(['git', 'diff', '--', c['implementation']], cwd=candidate, env=self.env))
        self.patch_hash = hashlib.sha256(self.patch_file.read_bytes()).hexdigest()
        self.landing = bee_events.build_event(attempt_id=self.aid, state='succeeded', transition_id='fixture-patch-arrived',
            feature_id=self.packet['feature_id'], job_id=c['job_id'], task_id=self.contract['id'], source_rev=self.base,
            coordinator='fixture-coordinator', backend='fixture', artifact_sha256=self.patch_hash,
            lease_sha256=self.lease['brief_sha256'], assigned_files=[c['implementation']])
        self.assertTrue(bee_events.record_landing(self.state, self.landing)['created'])
        self.assertFalse(bee_events.record_landing(self.state, self.landing)['created'])
        with contextlib.closing(self.open_ledger(self.db)) as db:
            self.assertEqual(RailsOutboxSource(self.state, ledger=db).replay()['emitted'], 1)
            self.assertEqual(RailsOutboxSource(self.state, ledger=db).replay()['duplicates'], 1)
        scanner = shutil.which('gitleaks')
        self.assertIsNotNone(scanner, 'offline campaign requires real gitleaks on PATH')
        # Private verifier-to-receiver channel in this same-process fixture.
        # Only the successful native write can emit a pin, before handoff assembly.
        written = []
        rec = verify_local.verify_and_commit(self.state, self.repo, self.aid, patch=self.patch_file.read_text(),
            declared_files=[c['implementation']], expected_patch_sha256=self.patch_hash,
            base_rev=self.base, tests=[c['test_id']], suite_command=self.suite, gitleaks=scanner, cacheable=False,
            contract_declared=True, acdd_preflight=lambda files: acdd_cli.verify_preflight(self.lease, self.state, files),
            runner=self.phase_check, reuse_record=False, on_receipt_written=written.append)
        self.receipt_pin, = written
        self.assertTrue(rec['ok']); self.assertEqual((rec['red']['exit_code'], rec['suite']['exit_code']), (1, 0))
        self.assertEqual(rec['gitleaks']['exit_code'], 0)
        self.assertEqual(rec['patch_sha256'], self.landing['data']['result']['artifact_sha256'])
        self.verified = rec['sha']
        checkout = self.root / 'review-checkout'
        self.git('worktree', 'add', '--detach', str(checkout), self.verified)
        tested = self.phase_check(checkout, self.suite + [c['test_file']])
        green = acdd_cli.record_green(self.state, self.preflight, checkout, tested, self.verified)
        self.assertEqual(green['criteria'][c['criterion']], 'passed')
        # Same pytest node ID, different test blob: a genuine passing run on the
        # *broken* baseline must not satisfy the frozen RED. Isolate its output.
        swapped = self.root / 'substitute-test'; swapped.mkdir()
        (swapped / c['implementation']).write_text(c['baseline'])
        (swapped / c['test_file']).write_text(c['approved_test'].replace('== 0', '== 1'))
        substitute = self.phase_check(swapped, self.suite + [c['test_id']])
        self.assertEqual(substitute['exit_code'], 0)
        with self.assertRaises(cli.CliError) as refused:
            acdd_cli.record_green(self.root / 'substitute-state', self.preflight, swapped, substitute, self.base)
        self.assertEqual(refused.exception.code, 'tests_tampered')
        for override, reason in [(dict(contract_sha256='0'*64), 'stale_revision'),
                                 (dict(base_rev=self.verified), 'stale_revision'),
                                 (dict(test_fingerprints={}), 'tests_tampered'),
                                 (dict(produced_by={'role':'worker'}), 'green_failed')]:
            with self.assertRaises(tdd.TddError) as caught:
                tdd.check_green(self.contract, self.contract_hash, self.red, dict(green, **override))
            self.assertEqual(caught.exception.code, reason)
        # Automated review has a concrete basis: inspect exact diff scope, test blob and observed result.
        self.assertEqual(self.git('diff', '--name-only', self.base, self.verified), c['implementation'])
        self.assertEqual(tdd.fingerprint_files(checkout,[c['test_file']]), self.red['test_fingerprints'])
        review = tdd.make_record(self.contract, self.contract_hash, phase='review', revision=self.verified,
            test_fingerprints=green['test_fingerprints'], command=['pytest','-q',c['test_file']],
            result=dict(exit_code=tested['exit_code'], timed_out=False, cases=tested['cases'], **tested['junit']),
            produced_by=dict(role='reviewer',name='fixture-review-check'), test_first=True,
            notes='Automated check of named test, unchanged test blob and changed-file scope. No independent approval.',
            attestation=tdd.coordinator_review_attestation('fixture-review-check','reviewer'))
        tdd.write_record(self.state, review, self.key)
        # An apparently green, unsigned record with identical criterion, contract and revision must stay a claim.
        claims = self.state / 'worker-claims'; claims.mkdir()
        (claims/'claim.json').write_bytes(canonical(dict(green, produced_by={'role':'worker','name':'fixture-worker'})))
        items = acdd_cli.integrate_preflight(self.state, [self.aid])
        job = jobs.load_job(self.state, c['job_id'])
        # Local driver hands the actual verification commit to integration. No remote dispatch.
        job['tasks'][0].update(state='verified', attempts=[self.aid], evidence=rec['sha'])
        jobs.save_job(self.state, job)
        self.wave = integrate_job.integrate(self.state, job, self.repo, suite_command=self.suite, runner=self.phase_check,
                                            cacheable=False)['record']
        self.assertTrue(self.wave['accepted']); self.integrated = self.wave['head_sha']
        self.assertNotEqual(self.verified, self.integrated)
        self.git('merge-base', '--is-ancestor', self.verified, self.integrated)
        self.assertEqual(self.git('rev-parse', integrate_job.integration_ref(c['job_id'])), self.integrated)
        self.git('checkout', '--detach', self.integrated, cwd=checkout)
        run = self.phase_check(checkout, self.suite)
        statuses = acdd_cli.record_integration(self.state, items, checkout, run, self.integrated)
        self.assertEqual(statuses, [(self.contract['id'], 'valid')])
        recovered = jobs.load_job(self.state, c['job_id'])
        self.assertEqual(recovered['integration']['last_commit'], self.integrated)
        jobs.save_job(self.state, recovered)
        self.assertGreater(self.campaign_import(), 0)
        self.assertEqual(self.campaign_import(), 0)

    def campaign_checks(self, port, owner, env):
        with contextlib.closing(self.open_ledger(self.db, read_only=True)) as db:
            self.local_rows = [json.loads(r['envelope_json']) for r in db.query('SELECT envelope_json FROM event_rows ORDER BY ingest_seq')]
        self.phases, self.observed = {}, []
        route = '/api/rizzstack/rails/'
        for event in self.local_rows:
            if event['kind'] not in ('attempt.state','verification.result','review.result','merge.result'):
                continue
            eid = event['event_id']; params = urlencode(dict(kind='event',id=eid,format='json'))
            item, = json_ok(port, route + 'events?' + params, owner, origin=True)['items']
            view = json_ok(port, route + 'view?' + params, owner, origin=True)
            mark, = [m for lane in view['lanes'] for m in lane['marks']]
            cli = subprocess.check_output([sys.executable, '-m','bundlebees_plugin.rails_cli','query','--kind','event',
                                           '--id',eid,'--format','json'], cwd=BB, env=env, timeout=10)
            self.assertEqual(json.loads(cli)['items'], [item]); self.assertEqual(mark['event_id'], eid)
            self.assertEqual(item['origin_hash'], event['hash'])
            self.observed.append(item)
            if event['kind'] == 'verification.result' and event['authority']=='verifier_record':
                self.phases[item['phase']] = item
        self.assertEqual([(r['phase'],r['code_rev'],r['outcome']) for r in self.phases.values()],
                         [('red',self.base,'EXPECTED_RED'), ('green',self.verified,'PASS'), ('integration',self.integrated,'PASS')])
        for r in self.phases.values():
            self.assertEqual((r['contract_sha256'],r['ac_id']), (self.contract_hash,self.coding['criterion']))
            self.assertTrue(r['evidence_refs'])
        claim, = [r for r in self.observed if r['authority']=='worker_report' and r['kind']=='verification.result']
        self.assertEqual((claim['outcome'],claim['current']), ('UNVERIFIED',False))
        landing, = [e for e in self.local_rows if e['kind']=='attempt.state']
        self.assertEqual((landing['source']['record_id'], landing['scope']['attempt_id'], landing['scope']['code_rev'],
                          landing['authority'], landing['payload']['to_state']),
                         (self.landing['id'], self.aid, self.base, 'worker_report', 'succeeded'))
        review, = [r for r in self.observed if r['kind']=='review.result']
        self.assertEqual((review['independent'], review['reviewed_head'], review['outcome']), (False, self.verified, 'UNVERIFIED'))
        merge, = [r for r in self.observed if r['kind']=='merge.result']
        self.assertEqual(merge['scope']['code_rev'], self.integrated)
        self.assertFalse(any(e['kind']=='acceptance.result' for e in self.local_rows))
        # Physical local receipt order, not untrusted event timestamps, proves interleaving.
        seqs = [row['seq'] for row in self.local_rows if row['kind']=='source.checkpoint' and
                row['source']['adapter']=='rails_import']
        self.assertEqual(len(seqs), 2)
        sequence = lambda phase: int(self.phases[phase]['event_id'].rsplit(':',1)[1])
        self.assertLess(sequence('red'), seqs[0]); self.assertLess(seqs[-1], landing['seq'])
        self.assertLess(landing['seq'], sequence('green'))
        return self.phases['integration']['event_id']

    def campaign_handoff(self, feedback_id):
        from bundlebees_plugin import rails_return, return_report
        job, ac = self.coding['job_id'], self.coding['criterion']
        with contextlib.closing(self.open_ledger(self.db, read_only=True)) as db:
            local_head = db.head()
        verify_origin(self.local_rows, local_head)
        self.check_wire(self.local_rows)
        self.assertEqual(self.local_rows[-1]['event_id'], feedback_id)
        # The launcher can attest only to its leased BASE. Its tool observation and
        # native EXPECTED_RED can share a sidecar; GREEN and integration cannot be relabelled.
        selected = [self.tool_ids[-1], self.phases['red']['event_id']]
        cfg = dict(schema=rails_return.INPUT_SCHEMA, job_id=job, task_id=self.contract['id'], code_rev=self.base,
                   contract_sha256=self.contract_hash, workers=[self.head], coordinator=local_head, evidence={ac:selected})
        anchors = self.root / 'anchors.json'
        anchors.touch(mode=0o600)
        def build(value):
            anchors.write_bytes(canonical(value))
            return return_report.build(self.state, job, repo=self.repo, rails_db=self.db, rails_anchors=anchors)

        claim, = [r for r in self.observed if r['authority']=='worker_report' and r['kind']=='verification.result']
        for change in (dict(contract_sha256='0'*64), dict(code_rev=self.integrated),
                       dict(workers=[dict(self.head, hash='0'*64)]), dict(coordinator=dict(local_head, hash='0'*64)),
                       dict(evidence={ac:[selected[0], self.phases['green']['event_id']]}),
                       dict(evidence={ac:[selected[0], claim['event_id']]}), dict(evidence={ac:['absent:1']})):
            with self.assertRaises(return_report.ReturnError) as caught:
                build(dict(cfg, **change))
            self.assertEqual(caught.exception.code, 'rails_evidence_refused')
        self.assertFalse(return_report.return_path(self.state, job).exists())
        native = return_report.build(self.state, job, repo=self.repo)
        manifest = build(cfg)
        directory = return_report.return_dir(self.state, job)
        data = (directory / rails_return.FILE).read_bytes()
        side = json.loads(data)
        self.assertEqual(validate_schema(side, load_json(SCHEMAS / 'evidence.schema.json')), [])
        self.assertEqual(side['verification_links'], [dict(ac_id=ac, event_id=selected[1], verdict='EXPECTED_RED')])
        self.assertEqual(set(side['selected_event_ids']), set(selected))
        self.assertEqual((side['code_rev'], side['contract_sha256']), (self.base, self.contract_hash))
        self.assertEqual(side['origin_heads'], [local_head, self.head])
        self.assertEqual(side['imported_checkpoints'], [dict(self.head, source='rails_import')])
        self.assertEqual((manifest['verification']['commit'], manifest['integration']['commit']), (self.verified,self.integrated))
        self.assertEqual((manifest['receiver_decision']['status'],side['receiver_decision']), ('pending','pending'))
        self.assertTrue(manifest['pending_approvals']); self.assertEqual(side['intervention_count'], 0)
        ref = f'jobs/{job}/{rails_return.FILE}#sha256={hashlib.sha256(data).hexdigest()}'
        row, = manifest['acceptance']; prior, = native['acceptance']
        self.assertEqual((row['id'], row['status'], prior['status']), (ac, 'PASS', 'PASS'))
        self.assertEqual(row['evidence'], [*prior['evidence'], ref]); self.assertTrue(prior['evidence'])
        self.assertIn(ref, (directory / 'RETURN.md').read_text())
        self.assertTrue(return_report.verify(self.state, job, repo=self.repo, rails_db=self.db, rails_anchors=anchors)['ok'])

        # Preserve the packet's native state-relative evidence layout, never the lease key, DB or HOME.
        out = Path(os.environ.get('RAILS_R18_CAMPAIGN_DIR', self.root / 'coding-return'))
        out.mkdir(mode=0o700, exist_ok=False)
        for path in [directory / name for name in ('return.json','RETURN.md',rails_return.FILE)] + [*self.state.glob('evidence/*/*.json'),
                     *self.state.glob('waves/*.json'), *self.state.glob('verify-results/*.json'),
                     *self.state.glob('packets/*.json'), *self.state.glob('authorizations/*.json'),
                     *self.state.glob('events/outbox/*.json')]:
            if not path.is_file():
                continue
            dest = out / path.relative_to(self.state)
            dest.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(path, dest)
        shutil.copyfile(self.patch_file, out / 'candidate.patch')
        self.git('bundle', 'create', str(out.resolve() / 'fixture.bundle'), '--all')
        receiver = self.root / 'receiver.git'
        self.git('clone', '--mirror', str(out.resolve() / 'fixture.bundle'), str(receiver))
        for rev, text in ((self.base, self.coding['baseline']), (self.verified, self.coding['candidate']),
                          (self.integrated, self.coding['candidate'])):
            self.assertEqual(self.git('show', f"{rev}:{self.coding['implementation']}", cwd=receiver), text.rstrip())
        heads = {repo.name:self.git('rev-parse', 'HEAD', cwd=repo) for repo in (ROOT, HYVV, BB, ORBIT)}
        for name, value in [('run-provenance', self.provenance(heads)), ('anchors', cfg), ('exported-origin', self.events),
                            ('coordinator-origin', self.local_rows), ('projected-results', self.observed),
                            ('browser-selection', self.browser_selection)]:
            (out / (name + '.json')).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

        # Pinned inputs are read independently of the producer's RETURN and sidecar.
        # Only the synthetic fixture exposes an optional external receiver capture.
        # Never reconstruct these fields from the handoff that they must authenticate.
        capture = os.environ.get('RAILS_R18_RECEIVER_CAPTURE')
        if capture:
            target = Path(capture).resolve()
            self.assertFalse(target.is_relative_to(out.resolve()))
            dispatch = {k:self.lease[k] for k in ('attempt_id','dispatch_chain_id','source_rev')}
            dispatch['brief'] = {k:self.lease['brief'][k] for k in ('job_id','task_id','contract_sha256')}
            with target.open('x', encoding='utf8') as stream:
                json.dump(dict(workflow=heads[ROOT.name], anchors=cfg, packet_digest=hashlib.sha256(canonical(self.packet)).hexdigest(),
                               dispatch=dispatch, receipt=self.receipt_pin._asdict(),
                               fixture_bundle_sha256=hashlib.sha256((out/'fixture.bundle').read_bytes()).hexdigest()),
                          stream, indent=2, sort_keys=True)
                stream.write('\n')
        def receive(root, receipt_pin=self.receipt_pin):
            return self.receive_campaign(root, receiver, cfg, hashlib.sha256(canonical(self.packet)).hexdigest(),
                                         receipt_pin)

        receive(out)
        self.refuse_substitutions(out, receive, claim['event_id'])
        # An authentic byte commitment is inapplicable if any scope field differs.
        for field, other in (('job_id', 'other-job'), ('task_id', 'other-task'), ('contract_sha256', 'a'*64),
                             ('attempt_id', 'att_1212121212121212'), ('base_rev', 'b'*40), ('commit', 'c'*40)):
            with self.subTest(foreign_pin=field), self.assertRaisesRegex(AssertionError, 'foreign verifier pin'):
                receive(out, self.receipt_pin._replace(**{field: other}))
        receive(out)  # the real delivery is still intact and pending
        (out / 'handoff-scope.json').write_text(json.dumps(dict(
            scope='offline coding fixture; test-only operator dispatch binding, synthetic admission and launcher journal; automated reviewer only',
            pending_approvals=manifest['pending_approvals'], native_manifest_schema_error_paths=[],
            native_return_reverified=True, receiver_decision='pending'), indent=2) + '\n')

    def receive_campaign(self, root, git_mirror, pins, packet_digest, receipt_pin):
        """Read only the delivered files, fixture Git objects and separately captured pins. No issuer DB/key."""
        from jsonschema import Draft202012Validator
        from tools import return_manifest

        def resolve(ref):
            path = (root / ref).resolve(strict=True)
            self.assertTrue(not Path(ref).is_absolute() and path.is_relative_to(root.resolve()) and path.is_file())
            return path

        job = pins['job_id']
        manifest = load_json(resolve(f'jobs/{job}/return.json'))
        # Never normalize or re-seal received bytes to make a native manifest pass.
        return_manifest.validate(manifest)
        Draft202012Validator(load_json(ROOT / 'schemas/return-manifest.schema.json')).validate(manifest)
        packet = load_json(resolve(f'packets/{job}.json'))
        sha = lambda data: hashlib.sha256(data).hexdigest()
        self.assertEqual(sha(canonical(packet)), packet_digest)
        self.assertEqual(manifest['packet_digest'], packet_digest)
        self.assertEqual((manifest['workflow_ref'], manifest['job_id']), (packet['workflow_ref'], job))
        auth = manifest['authorization']; admission = load_json(resolve(auth['reference']))['body']
        self.assertEqual((admission['job_id'], admission['base_rev'], admission['repo']),
                         (job, pins['code_rev'], packet['repository']['identity']))
        self.assertEqual((auth['authority'], auth['approved_by'], auth['approved_at']),
                         ('m1-authorization', admission['by'], admission['at']))
        self.assertIn('- receiver decision: `pending`', resolve(f'jobs/{job}/RETURN.md').read_text().splitlines())
        contract = packet['contract']
        self.assertEqual(sha(canonical({k:v for k,v in contract.items() if k != 'review'})), pins['contract_sha256'])
        self.assertEqual(manifest['contract'], {'id':contract['id'], 'sha256':pins['contract_sha256']})
        self.assertEqual(manifest['repository']['source_rev'], pins['code_rev'])
        self.assertEqual(manifest['receiver_decision'], return_manifest.pending_receiver_decision())
        self.assertEqual(set(manifest['pending_approvals']), set(packet['human_gates']))
        row, = manifest['acceptance']; criterion, = contract['acceptance_criteria']
        self.assertEqual((row['id'], row['tests'], row['status']), (criterion['id'], criterion['tests'], 'PASS'),
                         'substituted approved tests')
        verify, wave = manifest['verification'], manifest['integration']
        # Byte identity comes from the verifier's independent write-time pin.
        # A source.error about this file intentionally carries no fingerprint.
        self.assertEqual((receipt_pin.job_id, receipt_pin.task_id, receipt_pin.contract_sha256,
                          receipt_pin.attempt_id, receipt_pin.base_rev, receipt_pin.commit),
                         (job, pins['task_id'], pins['contract_sha256'], self.lease['attempt_id'],
                          pins['code_rev'], verify['commit']), 'foreign verifier pin')
        self.assertEqual(verify['record_path'], f'verify-results/{receipt_pin.attempt_id}.json')
        receipt_bytes = resolve(verify['record_path']).read_bytes()
        self.assertTrue(secrets.compare_digest(sha(receipt_bytes), receipt_pin.sha256),
                        'substituted verification receipt bytes')
        verification = json.loads(receipt_bytes)
        self.assertEqual(verification['attempt_id'], receipt_pin.attempt_id)
        self.assertEqual((verification['sha'], verification['base_rev'], verification['tests']),
                         (verify['commit'], pins['code_rev'], criterion['tests']))
        self.assertEqual((verify['suite']['result'], verify['gitleaks']['result']), ('PASS', 'PASS'))
        self.assertEqual((verification['suite']['exit_code'], verification['gitleaks']['exit_code']), (0, 0))
        wave_record = load_json(resolve(wave['evidence']))
        self.assertEqual(sha(canonical(wave_record)), wave['accepted_wave_digest'])
        self.assertTrue(wave_record['accepted']); self.assertEqual(wave_record['head_sha'], wave['commit'])
        self.assertEqual(wave_record['wave_id'], wave['wave'])
        self.git('merge-base', '--is-ancestor', verify['commit'], wave['commit'], cwd=git_mirror)

        worker = load_json(resolve('exported-origin.json')); local = load_json(resolve('coordinator-origin.json'))
        verify_origin(worker, pins['workers'][0]); verify_origin(local, pins['coordinator'])
        events = {e['event_id']:e for e in [*worker, *local]}
        merge, = [e for e in local if e['kind'] == 'merge.result' and e['authority'] == 'coordinator_record'
                  and e['source']['adapter'] == 'bundlebees' and e['scope']['task_id'] == wave['wave']]
        self.assertEqual((merge['payload']['status'], merge['scope']['code_rev'], merge['source']['revision']),
                         ('merged', wave['commit'], sha(resolve(wave['evidence']).read_bytes())))
        refs = manifest['red_green']
        side_ref, = [ref for ref in row['evidence'] if '#sha256=' in ref]
        self.assertCountEqual(row['evidence'], [refs['green']['record_path'], verify['record_path'], side_ref])
        path, digest = side_ref.split('#sha256='); side_file = resolve(path)
        self.assertEqual(path, f'jobs/{job}/rails-evidence.json')
        self.assertEqual(sha(side_file.read_bytes()), digest, 'wrong sidecar bytes')
        side = load_json(side_file)
        Draft202012Validator(load_json(SCHEMAS / 'evidence.schema.json')).validate(side)
        self.assertEqual(side['origin_heads'], [pins['coordinator'], *pins['workers']])
        self.assertEqual(side['imported_checkpoints'], [dict(pins['workers'][0], source='rails_import')])
        self.assertEqual((side['code_rev'], side['contract_sha256'], side['receiver_decision']),
                         (pins['code_rev'], pins['contract_sha256'], 'pending'))
        link, = side['verification_links']; linked = events[link['event_id']]
        self.assertEqual((linked['kind'], linked['authority']), ('verification.result', 'verifier_record'),
                         'worker observation cannot supply verifier authority')
        self.assertEqual((link['ac_id'], link['verdict']), (row['id'], 'EXPECTED_RED'))
        self.assertCountEqual(side['selected_event_ids'], pins['evidence'][row['id']])
        self.assertIn(link['event_id'], side['selected_event_ids'])
        # The test operator retained the assignment at setup, independently of
        # the delivered sidecar, origin rows and post-run anchor/selection file.
        dispatch = self.lease
        tool, = [e for e in worker if e['event_id'] in side['selected_event_ids']]
        self.assertEqual((tool['chain_id'], tool['scope']['attempt_id'], job, pins['task_id'],
                          side['contract_sha256'], side['code_rev']),
                         (dispatch['dispatch_chain_id'], dispatch['attempt_id'], dispatch['brief']['job_id'],
                          dispatch['brief']['task_id'], dispatch['brief']['contract_sha256'], dispatch['source_rev']))
        for phase, rev in [('red', pins['code_rev']), ('green', verify['commit'])]:
            ref = refs[phase]; file = resolve(ref['record_path']); record = load_json(file)
            self.assertEqual((ref['phase'], ref['revision']), (phase, rev))
            self.assertEqual(sha(file.read_bytes()), ref['sha256'], 'substituted evidence bytes')
            origin, = [e for e in local if e['kind']=='verification.result' and e['authority']=='verifier_record'
                       and e['payload']['phase']==phase]
            self.assertEqual((origin['source']['revision'], origin['scope']['code_rev'], origin['scope']['contract_sha256']),
                             (sha(file.read_bytes()), rev, pins['contract_sha256']))
            if phase == 'red':
                self.assertEqual(linked, origin)
            self.assertEqual((record['phase'], record['revision'], record['contract_sha256'], record['produced_by']['role']),
                             (phase, rev, pins['contract_sha256'], 'verifier'))
            self.assertEqual([c['id'] for c in record['result']['cases']], criterion['tests'])
            result = record['result']; expect = 'failed' if phase == 'red' else 'passed'
            self.assertEqual((record['criteria'][row['id']], result['cases'][0]['outcome']), (expect, expect))
            self.assertEqual((result['tests'], result['exit_code'], result['skipped'], result['errors'], result['timed_out']),
                             (1, int(phase == 'red'), 0, 0, False))
            test_file, = contract['scope']['test_files']
            blob = subprocess.check_output(['git', 'show', f'{rev}:{test_file}'], cwd=git_mirror, env=self.env)
            self.assertEqual(blob, self.coding['approved_test'].encode(), 'substituted approved test blob')
            self.assertEqual(record['test_fingerprints'], {test_file:sha(blob)})

    def refuse_substitutions(self, out, receive, worker_claim_id):
        from tools import return_manifest
        # Re-seal edited *copies*: failure must be the replacement, not stale manifest integrity.
        for change in ('test', 'evidence', 'receipt', 'authority', 'decision'):
            with self.subTest(change=change):
                scratch = shutil.copytree(out, self.root / f'substitution-{change}')
                path, = scratch.glob('jobs/*/return.json'); doc = load_json(path); row, = doc['acceptance']
                if change == 'test':
                    row['tests'] = ['test_substitute.py::test_unrelated']
                    refusal = self.assertRaisesRegex(AssertionError, 'substituted approved tests')
                elif change == 'evidence':
                    files = doc['red_green']
                    shutil.copyfile(scratch/files['red']['record_path'], scratch/files['green']['record_path'])
                    refusal = self.assertRaisesRegex(AssertionError, 'substituted evidence bytes')
                elif change == 'receipt':
                    # Semantically identical receipt (same attempt, head, checks,
                    # etc.). Neither manifest resealing nor a replacement digest
                    # in the delivered anchors can bless different native bytes.
                    receipt = scratch / doc['verification']['record_path']
                    receipt.write_bytes(receipt.read_bytes() + b'\n')
                    anchors = scratch / 'anchors.json'
                    anchors.write_bytes(canonical(dict(load_json(anchors),
                        receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())))
                    refusal = self.assertRaisesRegex(AssertionError, 'substituted verification receipt bytes')
                elif change == 'authority':
                    side_path = path.with_name('rails-evidence.json'); side = load_json(side_path)
                    side['verification_links'][0]['event_id'] = worker_claim_id
                    side_path.write_bytes(canonical(side))
                    row['evidence'][-1] = f'{side_path.relative_to(scratch)}#sha256={hashlib.sha256(side_path.read_bytes()).hexdigest()}'
                    refusal = self.assertRaisesRegex(AssertionError, 'worker observation cannot supply verifier authority')
                else:
                    doc['receiver_decision']['status'] = 'accepted'
                    refusal = self.assertRaisesRegex(return_manifest.ReturnError, 'must stay pending')
                path.write_bytes(canonical(return_manifest.seal(doc)))
                with refusal:
                    receive(scratch)

    def check_wire(self, local_rows):
        event_schema = load_json(SCHEMAS / 'event.schema.json')
        kinds = load_json(SCHEMAS / 'payload.schema.json')['properties']['kinds']['properties']
        for event in [*self.events, *local_rows]:
            self.assertEqual(validate_schema(event, event_schema), [], event['event_id'])
            self.assertEqual(validate_schema(event['payload'], kinds[event['kind']]), [], event['event_id'])

    def write_return(self, feedback_id, result, view, *, keep):
        from rizzstack_rails import feedback
        selected = [*self.tool_ids, feedback_id]
        contract = (SCHEMAS / 'README.md').read_text().split('freeze-digest: ', 1)[1].split()[0]
        heads = {repo.name: subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=repo).strip()
                 for repo in (ROOT, HYVV, BB, ORBIT)}
        revision = heads[ROOT.name]
        with contextlib.closing(self.open_ledger(self.db, read_only=True)) as db:
            local_head = db.head()
            local_rows = [json.loads(r['envelope_json']) for r in db.query('SELECT envelope_json FROM event_rows ORDER BY seq')]
            verify_origin(local_rows, local_head)
            self.assertTrue(db.verify_chain()['legacy_ok'])
            self.assertEqual(local_rows[-1]['event_id'], feedback_id)
            self.assertEqual(local_rows[-1]['payload']['target_event_id'], self.tool_ids[-1])
            count = feedback.distinct_interventions(db)
            local_uuid = db.ledger_uuid
        # R02 commits the origin UUID as the last 36 characters of its chain ID.
        worker_uuid = self.head['chain_id'][-36:]
        gaps = [{'adapter': name, 'status': 'unavailable', 'gaps': [{'code': 'not_exercised'}]}
                for name in ('hermes-session', 'bundlebees-verifier', 'outbox')]
        self.check_wire(local_rows)
        limits = ['Local synthetic journal; execution backend idle. No real campaign or verifier links.',
                  'Feedback used the coordinator Python writer, not a browser submission or a human rating.',
                  'code_rev is the workflow base HEAD; run-provenance.json identifies the local source bytes.',
                  'Same-host copies are not independent witnesses against privileged rewrites.']
        if not hasattr(self, 'browser_selection'):
            limits.append('Browser inspection not run; set RAILS_R18_BROWSER_DIST for that check.')
        doc = dict(schema='rizzstack.rails-evidence/1', generated_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                   machines=[dict(alias='worker-1', role='worker'), dict(alias='coordinator-1', role='coordinator')],
                   ledgers=[dict(machine='worker-1', ledger_uuid=worker_uuid), dict(machine='coordinator-1', ledger_uuid=local_uuid)],
                   origin_heads=[self.head, local_head], imported_checkpoints=[self.checkpoint],
                   source_coverage=[dict(adapter='launcher-log', status='partial', gaps=[{'code':'fixture_only'}]), *gaps],
                   selected_event_ids=selected, code_rev=revision, contract_sha256=contract, redaction_policy='rails-safe/1',
                   intervention_count=count, verification_links=[], limitations=limits, receiver_decision='pending')
        def check(value):
            check_sidecar(value, self.events, self.head, local_head, self.checkpoint, selected, revision, contract)
        check(doc)
        for field in ('origin_heads', 'imported_checkpoints', 'code_rev', 'contract_sha256', 'selected_event_ids'):
            wrong = copy.deepcopy(doc)
            if field in ('origin_heads', 'imported_checkpoints'):
                wrong[field][0]['hash'] = '0' * 64
            elif field == 'selected_event_ids':
                wrong[field].pop()
            else:
                wrong[field] = '0' * len(wrong[field])
            with self.assertRaises(ValueError, msg=field):
                check(wrong)

        # Never overwrite an earlier run. Only these public, synthetic records leave the temp HOME.
        out = self.root / 'return'
        if keep and (configured := os.environ.get('RAILS_R18_EVIDENCE_DIR')):
            out = Path(configured)
        out.mkdir(mode=0o700, exist_ok=False)
        files = {
            'rails-evidence.json': doc, 'exported-origin.json': self.events,
            'coordinator-origin.json': local_rows, 'result.json': result, 'view.json': view,
            'run-provenance.json': self.provenance(heads),
        }
        if hasattr(self, 'browser_selection'):
            files['browser-selection.json'] = self.browser_selection
        for name, data in files.items():
            (out / name).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        (out / 'RETURN.md').write_text('# R18 local fixture handoff\n\nReceiver decision: pending.\n\n'
                                       '| Check | Evidence |\n|--|--|\n| Imported timeline and CLI | '
                                       '[rails-evidence.json](rails-evidence.json) |\n\nObservations only; '
                                       'this run has no authorized campaign RETURN manifest.\n', encoding='utf-8')
        check(load_json(out / 'rails-evidence.json'))

    @staticmethod
    def provenance(heads):
        # Record the relevant checkout bytes (including untracked files), not private config or a git diff.
        paths = {ROOT: ['tests/test_rails_acceptance.py', 'schemas/rails/fixtures/m1-scenario.json'],
                 HYVV: ['launcher.py', 'rails_*.py', 'contrib/rizzstack_rails/*.py'],
                  BB: ['bundlebees_plugin/rails*.py', 'bundlebees_plugin/launcher*.py', 'contrib/rizzstack_rails/*.py',
                       *['bundlebees_plugin/'+n+'.py' for n in ('acdd_cli','contract','job','leases','packets','bee_events',
                                                                  'integrate_job','verify_local','tdd','return_report')]],
                  ORBIT: ['server/index.mjs', 'server/rails-proxy.mjs', 'src/rails-shell.ts', 'apps/rizzstack-rails/*.js',
                          'contrib/rails_server/*.py', 'contrib/rizzstack_rails/*.py']}
        return {repo.name: {'base_head': heads[repo.name], 'scope': 'selected local input files',
                            'sha256': {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for pattern in patterns for p in sorted(repo.glob(pattern))}}
                for repo, patterns in paths.items()}
