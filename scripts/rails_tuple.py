"""Gate a reviewed four-commit tuple on a disposable Linux runner (see --help).

Place *clean checkouts* named workflow, bundlebees, hyvv, orbitdesktop under one
parent. Supply an external JSON object with those four keys and full expected
commit IDs. Nothing in a candidate predicts its own SHA. Have Git, OpenSSH,
gitleaks 8.21.2, Node 22.12+ (ABI 127), npm and Python with pytest/jsonschema
on the runner. Preinstall setuptools and hatchling for offline wheel builds.
Keep scratch outside the checkouts. Do not run unreviewed code
on an owner host. For offline use, provision the lock-matched orbit-check kit
(contrib/core-review/orbit-check/README.md) plus a local CHROMIUM_EXECUTABLE:

  python3 -B workflow/scripts/rails_tuple.py --tuple tuple.json --out /scratch/run1 --orbit-kit /scratch/kit

Use fresh worktrees for each run. --ci-install instead installs from the Orbit
lock and Playwright's Chromium release on a disposable, networked CI worker.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


WORKFLOW = Path(__file__).resolve().parents[1]
ROOT = WORKFLOW.parent
REPOS = ('workflow', 'bundlebees', 'hyvv', 'orbitdesktop')
R18 = {'test_packet_and_wrong_head', 'test_import_restart_and_local_feedback', 'test_registered_proxy_cli_and_return',
       'test_browser_inspector_and_cli_identity', 'test_offline_coding_campaign'}
NATIVE = {  # Same reviewed Linux/amd64 binaries as orbit-check/dependency-kit.py
    'better-sqlite3/build/Release/better_sqlite3.node': 'df9fbd0d061f360d81fb51e265c53c9605020bd68219e34f33c07c85de15719a',
    'node-pty/build/Release/pty.node': '9b33df633d1dbd6a7e4d4ae11adca31a7d475c01421698abc9fdb564ec729e78',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def demand(condition, message):
    if not condition:
        raise ValueError(message)


def checkouts(expected, env, *, pristine):
    demand(set(expected) == set(REPOS), 'tuple must name exactly four repositories')
    for name in REPOS:
        repo = ROOT / name
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=repo, env=env, text=True).strip()
        demand(re.fullmatch('[0-9a-f]{40}', expected[name]) and git('rev-parse', 'HEAD') == expected[name],
               f'{name}: expected full SHA does not match HEAD')
        demand(repo.resolve() == repo and Path(git('rev-parse', '--show-toplevel')) == repo, f'{name}: not a checkout')
        flags = ['--ignored=matching'] if pristine else []
        dirty = git('status', '--porcelain=v1', '--untracked-files=all', *flags)
        demand(not dirty, f'{name}: expected a fresh checkout, first change: {dirty[:200]}')


def provision_kit(kit, work, orbit, env):
    # Re-address only transport, in a disposable staging lock. npm ci enforces
    # each tarball's integrity from the *candidate* lock, not a kit-generated lock.
    deps = kit / 'deps'
    lock = orbit / 'package-lock.json'
    demand(digest(lock) == (deps / 'lock.sha256').read_text().strip(), 'Orbit kit lock mismatch')
    staging = work / 'install'; staging.mkdir()
    shutil.copyfile(orbit / 'package.json', staging / 'package.json')
    locked = json.loads(lock.read_bytes())
    for key, package in locked['packages'].items():
        if key:
            alg, value = package['integrity'].split('-', 1)
            sha = base64.b64decode(value, validate=True).hex()
            demand(alg == 'sha512' and len(sha) == 128, 'unexpected lock integrity')
            package['resolved'] = (deps / 'tarballs' / (sha + '.tgz')).as_uri()
    write(staging / 'package-lock.json', locked)
    subprocess.run(['npm', 'ci', '--offline', '--include=dev', '--ignore-scripts', '--no-audit', '--no-fund'],
                   cwd=staging, env=env, check=True, timeout=600)
    for name, sha in NATIVE.items():
        src = deps / 'native' / name
        demand(digest(src) == sha, f'wrong native dependency: {name}')
        target = staging / 'node_modules' / name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, target)
    shutil.move(staging / 'node_modules', orbit / 'node_modules')


def junit(path, required=()):
    cases = list(ET.parse(path).iter('testcase'))
    counts = {'tests':len(cases), **{name:sum(c.find(tag) is not None for c in cases) for name, tag in
              [('failures','failure'), ('errors','error'), ('skipped','skipped')]}}
    demand(cases and set(required).issubset(c.get('name') for c in cases), f'{path.name}: missing required cases')
    return counts


def run(args, out, work, summary):
    pins = json.loads(args.tuple.read_bytes()); summary['tuple'] = pins
    home = work / 'home'; home.mkdir()
    env = dict(PATH=os.environ['PATH'], HOME=str(home), TMPDIR=str(work), LANG='C.UTF-8', PYTHONNOUSERSITE='1',
               PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', GIT_CONFIG_NOSYSTEM='1',
               GIT_TERMINAL_PROMPT='0', ORBIT_AGENT_DISCOVERY='off', ONNXRUNTIME_NODE_INSTALL='skip',
               RAILS_R18_REQUIRED='1', RAILS_R18_ROOT=str(ROOT), WORKFLOW_SRC=str(WORKFLOW),
                RAILS_R18_EVIDENCE_DIR=str(out/'trace'), RAILS_R18_CAMPAIGN_DIR=str(out/'campaign'),
                RAILS_R18_RECEIVER_CAPTURE=str(out/'receiver-pins.json'))
    checkouts(pins, env, pristine=True)
    orbit = ROOT / 'orbitdesktop'
    def output(argv, cwd=orbit):
        return subprocess.check_output(argv, cwd=cwd, env=env, text=True, timeout=60).strip()
    node, abi = output(['node','-p','process.versions.node+" "+process.versions.modules']).split()
    demand(node.startswith('22.') and int(node.split('.')[1]) >= 12 and abi == '127', 'expected Node 22.12+ / ABI 127')
    scan = output(['gitleaks','version'])
    demand(scan == '8.21.2', 'expected gitleaks 8.21.2')
    versions = summary['tools'] = dict(node=node, node_abi=abi, npm=output(['npm','--version']), gitleaks=scan,
        python=sys.version, python_packages=output([sys.executable, '-I', '-c',
        'from importlib.metadata import version; print(version("pytest"),version("jsonschema"))']),
        orbit_lock_sha256=digest(orbit/'package-lock.json'))
    if args.orbit_kit:
        provision_kit(args.orbit_kit.resolve(strict=True), work, orbit, env)
        chrome = Path(os.environ['CHROMIUM_EXECUTABLE']).resolve(strict=True)
        env['CHROMIUM_EXECUTABLE'] = str(chrome)
        versions.update(chromium=output([str(chrome),'--version']), chromium_sha256=digest(chrome))
    else:
        subprocess.run(['npm','ci','--include=dev','--no-audit','--no-fund'], cwd=orbit, env=env, check=True, timeout=600)
        env['PLAYWRIGHT_BROWSERS_PATH'] = str(work/'browsers')
        subprocess.run(['node','node_modules/playwright-core/cli.js','install','--with-deps','--only-shell','chromium'],
                       cwd=orbit, env=env, check=True, timeout=600)
    versions['native_modules'] = {name:digest(orbit/'node_modules'/name) for name in NATIVE}
    versions['sqlite'] = output(['node','-e', 'require("node-pty");const db=new(require("better-sqlite3"))(":memory:");'
                                 'console.log(db.prepare("select sqlite_version()").pluck().get());db.close()'])
    env.update(ORBIT_BUILD_SCRATCH=str(work), RAILS_R18_BROWSER_DIST=str(work/'dist'), ORBIT_RAILS_TEST_DIST=str(work/'dist'))

    def execute(label, repo, argv, xml=False, required=()):
        directory = ROOT/repo; log = out/(label+'.log'); report = out/(label+'.xml')
        # Separate processes and repository-specific imports. Never expose another
        # repository's vendor directory as a fallback for a missing dependency.
        local = dict(env, PYTHONPATH=os.pathsep.join(map(str,[directory, directory/'contrib'])))
        print(f'[{label}]', *argv, flush=True)
        with log.open('xb') as stream:
            proc = subprocess.run(argv, cwd=directory, env=local, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        if xml:
            summary['junit'][label] = counts = junit(report, required)
            demand(not any(counts[k] for k in ('skipped','errors','failures')), f'{label}: {counts}; see {log}')
        demand(proc.returncode == 0, f'{label}: exit {proc.returncode}; see {log}')

    execute('build', 'orbitdesktop', ['node','scripts/isolated_build.mjs','--dest',str(work/'dist')])
    execute('inventory','workflow',[sys.executable,'contrib/core-review/check_rails_delivery.py'])
    execute('vendor','bundlebees',[sys.executable,'scripts/vendor_rails.py','--check'])
    # Build the installed artifacts from the checked-out commits. Keep backend
    # output out of the checkouts and never resolve dependencies from the network.
    wheels = work / 'wheels'; wheels.mkdir()
    versions['wheel_builders'] = output([sys.executable, '-I', '-c',
        'from importlib.metadata import version; print(version("setuptools"),version("hatchling"))'])
    for repo, variable in [('bundlebees','BB_WHEEL'), ('hyvv','HYVV_WHEEL')]:
        source = work / ('build-' + repo)
        shutil.copytree(ROOT/repo, source, ignore=shutil.ignore_patterns('.git'))
        subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', 'wheel', '--no-index', '--no-deps',
                        '--no-build-isolation', '-w', str(wheels), str(source)], cwd=work,
                       env={**env, 'SOURCE_DATE_EPOCH':'1710000000'}, timeout=180, check=True)
        wheel, = wheels.glob(repo + '-*.whl')
        env[variable] = str(wheel)
        versions[repo + '_wheel_sha256'] = digest(wheel)
    # Discover all Rails modules in each repo, including producer/owner regressions.
    for repo in REPOS:
        suites = sorted(str(p.relative_to(ROOT/repo)) for p in (ROOT/repo/'tests').glob('test_rails_*.py'))
        demand(suites, f'{repo}: no Rails suites')
        if repo == 'bundlebees':
            suites.append('tests/test_return_conformance.py')
        if repo == 'workflow':
            suites.extend(['tests/test_return_manifest.py', 'contrib/core-review/test_core_usage_roundtrip.py'])
        execute(repo, repo, [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                            '--junitxml',str(out/(repo+'.xml')), *suites], xml=True, required=R18 if repo=='workflow' else ())
    suites = sorted(str(p.relative_to(orbit)) for p in (orbit/'tests').glob('rails-*.test.mjs'))
    demand(suites, 'missing Orbit Rails node suites')
    execute('orbit-node','orbitdesktop',['node','--test','--test-reporter=junit',
            '--test-reporter-destination='+str(out/'orbit-node.xml'), *suites], xml=True)
    execute('orbit-browser','orbitdesktop',[sys.executable,'tests/rails-live.browser.py'])
    for name in ('campaign','trace'):
        proof = json.loads((out/name/'browser-selection.json').read_bytes())
        demand(proof['selected_event_id'] and proof['browser_version'] and proof['dist_index_sha256']==digest(work/'dist/index.html'),
               f'{name}: missing browser/build evidence')
        heads = json.loads((out/name/'run-provenance.json').read_bytes())
        demand({k:v['base_head'] for k,v in heads.items()} == pins, f'{name}: tuple mismatch')
    checkouts(pins, env, pristine=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tuple', type=Path, required=True); parser.add_argument('--out', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--orbit-kit', type=Path); mode.add_argument('--ci-install', action='store_true')
    args = parser.parse_args(); out = args.out.resolve()
    demand(not any(out.is_relative_to(ROOT/r) for r in REPOS), 'use external scratch')
    os.umask(0o077); out.mkdir(mode=0o700, exist_ok=False)
    summary = {'passed':False, 'junit':{}, 'scope':'local four-checkout Rails gate; receiver decision pending'}
    try:
        with tempfile.TemporaryDirectory(dir=out.parent, prefix='rails-work-') as temp:
            run(args, out, Path(temp), summary)
        summary['passed'] = True
    finally:
        write(out/'summary.json', summary)
        # No circular checksum, no transient DBs, install trees, Home or private keys.
        files = sorted(p for p in out.rglob('*') if p.is_file())
        (out/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(out)}\n' for p in files))
        print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
