"""Verify a published *synthetic R18 fixture* using its exact clean Workflow checkout.

No worker, database, signer, network, browser or production receipt required.
Pass the evidence directory and Workflow checkout path. Inputs are the trusted
reviewer's capture in receiver-pins.json and the untrusted campaign/ tree.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def run():
    evidence, workflow = (Path(p).resolve(strict=True) for p in sys.argv[1:])
    expected = json.loads((evidence/'receiver-pins.json').read_bytes())
    if subprocess.check_output(['git','rev-parse','HEAD'], cwd=workflow, text=True).strip() != expected['workflow']:
        raise ValueError('wrong Workflow verifier commit')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'], cwd=workflow).strip():
        raise ValueError('use a clean, disposable Workflow checkout')
    sys.path.insert(0, str(workflow))
    from tests.test_rails_acceptance import LocalSlice, SCENARIO

    coding = json.loads(SCENARIO.read_bytes())['coding_campaign']
    campaign = evidence/'campaign'
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); mirror = tmp/'fixture.git'
        env = dict(HOME=str(tmp), PATH=os.environ['PATH'], LANG='C.UTF-8',
                   GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_ALLOW_PROTOCOL='file', GIT_TERMINAL_PROMPT='0',
                   PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
        bundle = campaign/'fixture.bundle'
        if hashlib.sha256(bundle.read_bytes()).hexdigest() != expected['fixture_bundle_sha256']:
            raise ValueError('fixture Git bundle differs from reviewer capture')
        subprocess.run(['git','clone','-q','--mirror',str(bundle),str(mirror)],env=env,check=True,timeout=20)
        case = LocalSlice(); case.env, case.coding = env, coding
        case.receive_campaign(campaign, mirror, expected['anchors'], expected['packet_digest'])
        result = json.loads((campaign/'jobs'/coding['job_id']/'return.json').read_bytes())
        observations = []
        for name,rev,code in [('baseline', result['repository']['source_rev'], 1),
                              ('verified', result['verification']['commit'], 0),
                              ('integrated', result['integration']['commit'], 0)]:
            work = tmp/name; work.mkdir()
            # Do not check out or execute arbitrary files from a delivered repository.
            for field, value in [('test_file','approved_test'),
                                 ('implementation','baseline' if code else 'candidate')]:
                filename = coding[field]
                if filename not in {'test_score.py','score.py'}: raise ValueError('unknown fixture')
                raw = subprocess.check_output(['git','show',f'{rev}:{filename}'],env=env,cwd=mirror,timeout=10)
                if raw != coding[value].encode(): raise ValueError('not the frozen synthetic source')
                (work/filename).write_bytes(raw)
            junit = work/'results.xml'
            proc = subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                                   '--junitxml',str(junit),coding['test_id']], cwd=work,env=env,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
            rows = list(ET.parse(junit).iter('testcase'))
            if (proc.returncode != code or len(rows) != 1 or rows[0].get('name') != 'test_empty_score'
                or rows[0].find('error') is not None or rows[0].find('skipped') is not None
                or (rows[0].find('failure') is not None) != bool(code)):
                raise ValueError(f'{name}: expected frozen test did not execute as recorded')
            observations.append({'stage':name,'revision':rev,'expected_exit':code,'observed_exit':proc.returncode})
        print(json.dumps({'verified':True,'native_digest':result['evidence_digest'],
                          'executions':observations,'decision':result['receiver_decision']},indent=2))


if __name__ == '__main__':
    run()
