"""Snapshot PR checks against an expected SHA tuple (read-only GitHub API).

Usage: python3 pr_checks.py /path/to/tuple.json > checks.json
Returns 1 for a changed head, a failed or pending job, no jobs, or a missing
required context. A passing result is only the per-repository CI gate.
"""
import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys


PRS = {'workflow': 91, 'bundlebees': 82, 'hyvv': 26, 'orbitdesktop': 46}


def gh(*args):
    return json.loads(subprocess.check_output(['gh', *args], timeout=90))


def snapshot(repo, expected):
    target = 'mojomast/' + repo
    pr = gh('pr', 'view', str(PRS[repo]), '-R', target, '--json',
            'url,state,isDraft,headRefOid,baseRefName,mergeable,reviewDecision,statusCheckRollup')
    rules = gh('api', f'repos/{target}/rules/branches/{pr["baseRefName"]}')
    required = {c['context'] for r in rules if r['type'] == 'required_status_checks'
                for c in r['parameters']['required_status_checks']}
    jobs = []
    for x in pr.pop('statusCheckRollup'):
        jobs.append({'name': x.get('name') or x.get('context'),
                     'status': x.get('conclusion') or x.get('state') or x.get('status'),
                     'url': x.get('detailsUrl') or x.get('targetUrl'),
                     'workflow': x.get('workflowName')})
    missing = sorted(required - {j['name'] for j in jobs if j['status'] == 'SUCCESS'})
    passed = (pr['state'] == 'OPEN' and pr['headRefOid'] == expected and bool(jobs) and not missing and
              all(j['status'] == 'SUCCESS' for j in jobs))
    return {**pr, 'expected': expected, 'jobs': jobs, 'ruleset_contexts': sorted(required),
            'missing_required_success': missing, 'all_reported_jobs_passed': passed}


def main():
    pins = json.loads(Path(sys.argv[1]).read_bytes())
    if set(pins) != set(PRS) or not all(re.fullmatch('[0-9a-f]{40}', h) for h in pins.values()):
        raise ValueError('expected four full commit IDs')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {r: pool.submit(snapshot, r, h) for r, h in pins.items()}
        repos = {r: f.result() for r, f in futures.items()}
    ok = all(p['all_reported_jobs_passed'] for p in repos.values())
    print(json.dumps({'observed_at': datetime.now(timezone.utc).isoformat(), 'success': ok, 'repos': repos},
                     sort_keys=True, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
