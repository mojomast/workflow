"""Offline M2 rehearsal. From workflow: python3 -B contrib/core-review/rehearse_m2.py

No connection settings, live identities, job authorizations or dispatch adapter.
The only Git transport is file://; all writable state is temporary. Stdout is a
review observation, not a provisioning receipt, TDD record or RETURN manifest.
"""
from contextlib import contextmanager
from hashlib import sha256
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / 'workflow'
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'hyvv'), str(ROOT / 'bundlebees'), str(WF / 'tests')]
import launcher
import test_m2_canary_prep as prep
from bundlebees_plugin import contract, contract_gate, job, provision_bind, provisioning, tools

PROJECT = 'm2-offline-fixture'
REPO = 'offline/' + PROJECT
HOST = 'offline-fixture-host'
OTHER = {'sibling': {'repo': 'offline/sibling'}}


def check(condition, why):
    if not condition:
        raise ValueError(why)


def refused(code, operation, exc_type):
    try:
        operation()
    except exc_type as exc:
        check(exc.code == code, f'expected {code}; got {exc.code}')
        return exc.code
    raise ValueError(f'expected refusal {code}')


def run(args, cwd, *, check_rc=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=check_rc, timeout=30)


def seed(work):
    rb = prep.RUNBOOK.read_text()
    packet = prep.parse_packet(prep.PACKET.read_text())
    c = prep.extract_runbook_contract(rb)
    row, = [s for s in json.loads((WF / 'plans/backlog.json').read_text())['slices']
            if s['id'] == 'M2-CANARY-RUN']
    pinned = row['brief']['source_rev']
    digest = contract.contract_sha256(dict(c, source_rev=pinned))
    check(digest in row['brief']['objective'], 'backlog/runbook digest drift')
    check(row['brief']['assigned_files'] == c['scope']['assigned_files'], 'lease drift')
    targets = {m[1]: m[3] for m in prep.AC_RE.finditer(prep.section_text(packet, 'Acceptance criteria'))}
    criteria = contract.criteria_tests(c)
    check(set(targets) == set(criteria) and all(targets[k] in v for k, v in criteria.items() if v),
          'packet/contract acceptance mismatch')

    step2 = rb.split('## Step 2 —', 1)[1].split('## Step 3 —', 1)[0]
    for name, lang in [('canary/__init__.py', 'python'), ('canary/meter.py', 'python'),
                       ('canary/report.py', 'python'), ('tests/test_meter.py', 'python'), ('README.md', 'markdown')]:
        match = re.search(r'^`' + re.escape(name) + r'`[^\n]*\n\n```' + lang + r'\n(.*?)^```$', step2, re.M | re.S)
        check(match is not None, f'no seed block for {name}')
        (work / name).parent.mkdir(exist_ok=True)
        (work / name).write_text(match[1])
    (work / 'tests/__init__.py').touch()
    run(['git', 'init', '-q', '-b', 'main'], work)
    run(['git', 'add', '.'], work)
    run(['git', 'commit', '-qm', 'local M2 seed'], work)
    base = run(['git', 'rev-parse', 'HEAD'], work).stdout.strip()
    # Never attach real authority (or an approval for the historical contract)
    # to a fixture. The synthetic seal is only for testing the contract gates.
    c.update(id=c['id'] + '-offline', source_rev=base,
             authorization=dict(c['authorization'], authorized=['offline gate checks only; zero bees']))
    frozen = contract.freeze_contract(c, approved_by='test-fixture:offline')
    return frozen, {'backlog_status': row['status'], 'backlog_base': pinned, 'runbook_hash_at_backlog_base': digest,
                    'acceptance_ids': list(criteria), 'seed_brief_has_contract_body': 'contract' in row['brief'],
                    'seed_brief_has_project': 'project' in row['brief']}


def exercise_suite(work, c):
    approved = work / c['scope']['test_files'][0]
    fingerprint = sha256(approved.read_bytes()).hexdigest()
    command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-v']
    red = run(command, work, check_rc=False)
    names = [t.rsplit('::', 1)[-1] for t in contract.red_set(c)]
    check(red.returncode == 1 and 'FAILED (errors=4)' in red.stderr and all(
        re.search(r'^' + re.escape(t) + r' \(.*\) .* ERROR$', red.stderr, re.M) for t in names)
        and red.stderr.count('NotImplementedError: canary.') == 4, 'unexpected seed test failures')
    fixes = {'canary/meter.py': '''    tally = {}
    for kind in events:
        if kind not in ("dispatch", "verify", "report", "integrate"):
            raise UnknownEventKind(kind)
        tally[kind] = tally.get(kind, 0) + 1
    return tally''', 'canary/report.py': '''    return "\\n".join(f"{key}={tally[key]}" for key in sorted(tally))'''}
    for name, impl in fixes.items():
        p = work / name
        old = p.read_text()
        text, count = re.subn(r'^    raise NotImplementedError\(.*\)$', lambda _: impl, old, flags=re.M)
        check(count == 1, f'expected one runbook stub in {name}')
        p.write_text(text)
    green = run(command, work)
    changed = run(['git', 'diff', '--name-only'], work).stdout.splitlines()
    check(changed == sorted(c['scope']['assigned_files']) and sha256(approved.read_bytes()).hexdigest() == fingerprint
          and all(re.search(r'^' + re.escape(t) + r' \(.*\) .* ok$', green.stderr, re.M) for t in names),
          'lease, approved tests or results changed')
    return {'approved_tests': names, 'test_file_sha256': fingerprint, 'lease_diff': changed,
            'manual_red': {'exit': red.returncode, 'stub_errors': 4},
            'local_reference_green': {'exit': green.returncode, 'passed': 4}}


@contextmanager
def local_api(worker, key):
    # No worker engine: only the real launcher's provisioning and registry
    # handlers. Limit the listener itself, not just the client's planned calls.
    handler = launcher.make_handler(worker, 'synthetic-only')

    class FixtureHandler(handler):
        def do_POST(self):
            if self.path not in (provisioning.PROVISION_PATH, provisioning.CLEANUP_PATH):
                return self._send(405, {'error': 'disabled_in_rehearsal'})
            super().do_POST()

        def do_GET(self):
            if self.path not in ('/v1/projects', provisioning.CAPABILITY_PATH, f'/v1/provision/receipts/{key}'):
                return self._send(405, {'error': 'disabled_in_rehearsal'})
            super().do_GET()

    # No environment-derived endpoint, proxy, redirect handling or credentials.
    with ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def transport(method, path, body=None):
            conn = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            try:
                conn.request(method, path, None if body is None else json.dumps(body),
                             {'Authorization': 'Bearer synthetic-only', 'Content-Type': 'application/json'})
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()

        try:
            yield transport
        finally:
            server.shutdown()
            thread.join()


def contract_probes(c, state_dir, projects):
    b = {'project': PROJECT, 'objective': 'offline contract checks only', 'source_rev': c['source_rev'],
         'assigned_files': c['scope']['assigned_files'], 'acceptance': list(contract.criteria_tests(c))}
    # Only read capability provided. No create/attempts methods, IDs or successful
    # dispatch stubs. A wrong-reason refusal fails the rehearsal.
    ctx = SimpleNamespace(bundlebees_client=SimpleNamespace(projects=projects), bundlebees_state_dir=state_dir,
                          get_config={'require_contract': True}.get)
    tool = tools._make_handler(ctx, 'bundlebees_dispatch')

    def probe(name, brief):
        result = json.loads(tool({'brief': brief}))
        check(result.get('ok') is False and result.get('code') == name, f'expected {name}: {result}')
        return result['code']

    cfg = {'require_contract': True}
    missing = probe('contract_missing', b)
    check(PROJECT in [p['name'] for p in projects()], 'missing-contract probe requires prior registration')
    return {'tool_missing': missing,
            'standalone_gate_missing': refused('contract_required', lambda: contract_gate.gate(b, config=cfg),
                                              contract_gate.ContractRefusal),
            'wrong_project': probe('project_unauthorized', dict(b, contract=c, project='unregistered')),
            'wrong_revision': probe('stale_revision', dict(b, contract=c, source_rev='f' * 40)),
            'test_in_lease': probe('tests_tampered', dict(b, contract=c, assigned_files=c['scope']['test_files'])),
            'edited_contract': probe('contract_changed', dict(b, contract=dict(c, title='changed'))),
            'valid_gate_only': contract_gate.gate(dict(b, contract=c), config=cfg)['mode']}


def register(tmp, work, c):
    profile = 'offline'
    policy_file, registry = tmp / 'policy.json', tmp / 'registry.json'
    profile_doc = {'repo_patterns': [REPO], 'workspace_root': str(tmp / 'workspaces'),
                   'mirrors': {REPO: work.as_uri()}, 'max_provisioned': 1, 'allow_cleanup': True}
    policy_file.write_text(json.dumps({'schema': provisioning.CAPABILITY_SCHEMA, 'profiles': {profile: profile_doc}}))
    registry.write_text(json.dumps({'projects': OTHER}))
    cfg = {'_config_path': str(registry), 'provisioning': {'enabled': True, 'policy': str(policy_file),
           'journal': str(tmp / 'journal'), 'credential_ready_repos': [REPO]}}
    worker = SimpleNamespace(attempts={}, cfg=cfg, provisioner=None)

    def restart():
        worker.cfg.update(json.loads(registry.read_text()))
        worker.provisioner = launcher.build_provisioner(worker.cfg)
        # Production's intentionally minimal git environment strips transport
        # overrides. Supply an equally local subprocess seam restricted to file.
        worker.provisioner.git = lambda args, cwd: run(['git', *args], cwd or tmp, check_rc=False)

    spec = {'repo': REPO, 'project': PROJECT, 'profile': profile, 'source_rev': c['source_rev'], 'host': HOST}
    fixture_job = {'job_id': 'offline-m2', 'tasks': [{'task_id': 'tally', 'provision': spec}]}
    task, = fixture_job['tasks']
    key = provision_bind.stable_key(fixture_job['job_id'], task['task_id'])
    req = provision_bind.request_for(fixture_job, task, spec, key)
    out = {}
    with local_api(worker, key) as transport:
        client = provisioning.HyvvProvisioner(transport, expect_host=HOST)
        out['disabled'] = refused('provisioning_disabled', client.capabilities, provisioning.ProvisionError)
        restart()
        projects = lambda: transport('GET', '/v1/projects')[1]['projects']
        lookup = lambda: client.authoritative_receipt(key, expect_project=PROJECT, expect_repo=REPO,
                     expect_rev=c['source_rev'], expect_host=HOST, expect_profile=profile)
        check(projects() == [{'name': 'sibling'}], 'nonempty fixture registry expected')
        out['unknown'] = refused('receipt_unknown', lookup, provisioning.ProvisionError)
        out['unenrolled'] = refused('profile_not_enrolled', lambda: client.provision(dict(req, profile='other')),
                                    provisioning.ProvisionError)
        out['no_job_authority'] = refused('authorization_missing', lambda: provision_bind.advance(
            tmp / 'job-state', fixture_job, provisioner=client), job.JobError)
        check(worker.provisioner.journal.all() == [], 'unexpected provisioning on a refusal')
        # Synthetic host-policy API exercise only. No job is created/authorized.
        receipt = client.provision(req)
        check(receipt.project == PROJECT and receipt.status == 'ready', 'wrong fixture receipt')
        check(client.provision(req) == receipt, 'idempotent provision did not replay the receipt')
        restart()
        fresh = lookup()
        binding = provisioning.Binding(repo=REPO, source_rev=c['source_rev'], profile=profile, project=PROJECT,
                    host=HOST, workspace=receipt.workspace, receipt_digest=receipt.digest,
                    contract_sha256=c['review']['contract_sha256'])
        binding.validate(fresh, contract_sha256=c['review']['contract_sha256'])
        out['after_restart'] = fresh.status
        workspace = Path(fresh.workspace)
        check(workspace == tmp / 'workspaces' / PROJECT and workspace.is_dir(), 'unexpected registered path')
        out['gate_probes'] = contract_probes(c, tmp / 'tool-state', projects)
        out['manual_suite'] = exercise_suite(work, c)
        (workspace / 'drift').touch()
        out['dirty_workspace'] = refused('receipt_stale', lookup, provisioning.ProvisionError)
        out['journal_after_drift'] = worker.provisioner.journal.read(key)['state']
        check(out['journal_after_drift'] == 'uncertain', 'dirty receipt should require reconciliation')
        out['cleanup'] = client.cleanup(PROJECT)['state']
        check(out['cleanup'] == 'cleaned' and not workspace.exists() and worker.cfg['projects'] == OTHER
              and json.loads(registry.read_text())['projects'] == OTHER, 'cleanup did not restore registry')
        check(not worker.attempts and not (tmp / 'tool-state').exists(), 'unexpected attempt/lease state')
        out['attempts'] = len(worker.attempts)
    return out


def main():
    with tempfile.TemporaryDirectory(prefix='m2-rehearsal-') as name:
        tmp = Path(name)
        work = tmp / 'seed'
        work.mkdir()
        env = {'PATH': os.defpath, 'HOME': name, 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_ALLOW_PROTOCOL': 'file', 'GIT_NO_LAZY_FETCH': '1',
               'GIT_TERMINAL_PROMPT': '0', 'GIT_AUTHOR_NAME': 'Offline Fixture',
               'GIT_AUTHOR_EMAIL': 'fixture@example.invalid', 'GIT_AUTHOR_DATE': '2000-01-01T00:00:00Z',
               'GIT_COMMITTER_NAME': 'Offline Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid',
               'GIT_COMMITTER_DATE': '2000-01-01T00:00:00Z', 'PYTHONDONTWRITEBYTECODE': '1'}
        with patch.dict(os.environ, env, clear=True), patch('socket.gethostname', return_value=HOST):
            c, source = seed(work)
            observation = register(tmp, work, c)
    print(json.dumps({'kind': 'offline-rehearsal-only', 'source': source, 'fixture_base': c['source_rev'],
                      'fixture_contract': c['review']['contract_sha256'], 'fixture': observation,
                      'real_canary': 'not_run', 'operator_acceptance': 'pending'}, indent=2))


if __name__ == '__main__':
    main()
