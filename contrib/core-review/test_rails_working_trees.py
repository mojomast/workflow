"""Run the named Rails packet tests from the four sibling repositories.

From workflow: python3 -B contrib/core-review/test_rails_working_trees.py
Uses the active Python (with pytest) and Node on PATH. Each repository gets
its own subprocess so vendored packages cannot mask missing dependencies in
another repository. Missing tests cause a nonzero exit, not empty discovery.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from check_rails_delivery import ROOT, check


def commands(r18_report: Path) -> list[tuple[str, list[str]]]:
    # Fixed commands, not shell strings or new commands read from a work packet.
    return [
        ('bundlebees', [sys.executable, 'scripts/vendor_rails.py', '--check']),
        ('workflow', [sys.executable, '-m', 'pytest', '-q', 'tests/test_rails_feasibility.py', 'tests/test_rails_contract.py']),
        ('bundlebees', [sys.executable, '-m', 'pytest', '-q', *['tests/test_rails_' + suite + '.py' for suite in (
            'ledger', 'importer', 'bundlebees_source', 'outbox_source', 'hermes_source', 'remote_source', 'query',
            'feedback', 'consumers', 'actions', 'registered', 'owner_bridge', 'return')]]),
        ('hyvv', [sys.executable, '-m', 'pytest', '-q', 'tests/test_rails_emission.py', 'tests/test_rails_native.py']),
        ('orbitdesktop', [sys.executable, '-m', 'pytest', '-q', 'tests/test_rails_vendor.py', 'tests/test_rails_http.py', 'tests/test_rails_append.py']),
        ('orbitdesktop', ['node', '--test', 'tests/rails-ui.test.mjs', 'tests/rails-proxy.test.mjs', 'tests/rails-feedback.test.mjs', 'tests/rails-owner-relay.test.mjs']),
        ('orbitdesktop', [sys.executable, 'tests/rails-live.browser.py']),
        ('workflow', [sys.executable, '-m', 'pytest', '-q', '--junitxml', str(r18_report), 'tests/test_rails_acceptance.py']),
    ]


if __name__ == '__main__':
    inventory = check(ROOT)
    failures = [] if inventory['inventory_complete'] else ['asset/parity inventory']
    if failures:
        print(json.dumps(inventory, indent=2), flush=True)
    env = {**os.environ, 'WORKFLOW_SRC': str(ROOT / 'workflow'), 'RAILS_R18_ROOT': str(ROOT),
           'RAILS_R18_REQUIRED': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    with tempfile.TemporaryDirectory(prefix='rails-packet-gate-') as temp:
        report = Path(temp) / 'r18.xml'
        for i, (repo, cmd) in enumerate(commands(report)):
            junit = None
            if cmd[1:3] == ['-m', 'pytest']:
                if '--junitxml' in cmd:
                    junit = report
                else:
                    junit = Path(temp) / f'{repo}-{i}.xml'
                    cmd = cmd + ['--junitxml', str(junit)]
            print(f'[{repo}]', *cmd, flush=True)
            try:
                rc = subprocess.run(cmd, cwd=ROOT / repo, env=env, timeout=900).returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                rc = type(exc).__name__
            if rc != 0:
                failures.append(f'{repo}/{Path(cmd[-1]).name}: {rc}')
            if junit is not None:
                cases = list(ET.parse(junit).iter('testcase')) if junit.exists() else []
                skipped = [case.get('name') for case in cases if case.find('skipped') is not None]
                if not cases or skipped:
                    failures.append(f'{repo}/{junit.name}: {len(cases)} collected, skipped: {skipped}')
    print(json.dumps({'failed_checks': failures}, indent=2))
    sys.exit(bool(failures))
