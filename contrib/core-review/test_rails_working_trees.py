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
            'feedback', 'consumers', 'actions', 'registered')]]),
        ('hyvv', [sys.executable, '-m', 'pytest', '-q', 'tests/test_rails_emission.py', 'tests/test_rails_native.py']),
        ('orbitdesktop', [sys.executable, '-m', 'pytest', '-q', 'tests/test_rails_vendor.py', 'tests/test_rails_http.py', 'tests/test_rails_append.py']),
        ('orbitdesktop', ['node', '--test', 'tests/rails-ui.test.mjs', 'tests/rails-proxy.test.mjs', 'tests/rails-feedback.test.mjs']),
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
        for repo, cmd in commands(report):
            print(f'[{repo}]', *cmd, flush=True)
            try:
                rc = subprocess.run(cmd, cwd=ROOT / repo, env=env, timeout=900).returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                rc = type(exc).__name__
            if rc != 0:
                failures.append(f'{repo}/{Path(cmd[-1]).name}: {rc}')
        cases = list(ET.parse(report).iter('testcase')) if report.exists() else []
        if not cases or any(case.find('skipped') is not None for case in cases):
            failures.append('R18 did not execute fully; see workflow/specs/rails-rollout.md for browser prerequisites')
    print(json.dumps({'failed_checks': failures}, indent=2))
    sys.exit(bool(failures))
