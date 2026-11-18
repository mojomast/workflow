"""Run the authenticated R12 measurement on a freshly seeded private fixture.

Usage: python3 -B fresh_http.py /four/checkouts tuple.json /private/scratch output.json [--indexed]
Requires the four clean detached review checkouts; tested on Linux/Python 3.13.
Does not accept an existing database, enrollment credential or network endpoint.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('trees', 'tuple', 'scratch', 'output'):
        p.add_argument(arg, type=Path)
    p.add_argument('--indexed', action='store_true')
    args = p.parse_args()
    trees, scratch = args.trees.resolve(), args.scratch.resolve()
    spec = json.loads(args.tuple.read_bytes())
    if not scratch.is_dir() or args.output.exists() or set(spec) != {'workflow','bundlebees','hyvv','orbitdesktop'}:
        raise ValueError('expected fresh output, prepared private scratch and exact tuple')
    sys.path.insert(0, str(trees/'workflow/scripts'))
    import bench_rails
    if bench_rails.revisions() != spec: raise ValueError('unexpected checkouts')
    os.umask(0o077)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        folder = Path(tmp)
        _, stats = bench_rails.seed(folder/'copy.sqlite', 100000, attempt_index=args.indexed)
        (folder/'orbitdesktop').symlink_to(trees/'orbitdesktop', target_is_directory=True)
        shutil.copyfile(Path(__file__).with_name('measure.py'),folder/'measure.py')
        env = dict(PATH=os.environ['PATH'], HOME=tmp, TMPDIR=tmp, LANG='C.UTF-8', PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([sys.executable,'-I','-B',str(folder/'measure.py'),'http','--samples','100'],
                       cwd=folder, env=env, check=True, timeout=900)
        report = json.loads((folder/'http.json').read_bytes())
        report.update(tuple=spec, seed=stats, indexed_before_seed=args.indexed)
        with args.output.open('x') as out: json.dump(report,out,indent=2); out.write('\n')
        # Evaluate the frozen gate, independently of a successful measurement.
        return int(not all(report[k+'_p95_ms'] <= 500 for k in ('events','view')))


if __name__ == '__main__':
    sys.exit(main())
