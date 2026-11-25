"""Build an offline npm-ci input using only authenticated package-lock tarballs."""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys

repo, cache = map(Path, sys.argv[1:])
deps = Path('deps')
pkg = repo / 'package.json'
lock = repo / 'package-lock.json'
for file in (pkg, lock):
    if file.is_symlink():
        raise SystemExit(f'unexpected symlink: {file.name}')
shutil.copyfile(pkg, deps / pkg.name)
(deps / 'lock.sha256').write_text(hashlib.sha256(lock.read_bytes()).hexdigest() + '\n')
data = json.loads(lock.read_text())
count = 0
for key, package in data['packages'].items():
    if not key:
        continue
    if not package['resolved'].startswith('https://registry.npmjs.org/'):
        raise SystemExit('expected a public npm package: ' + key)
    alg, encoded = package['integrity'].split('-', 1)
    digest = base64.b64decode(encoded, validate=True).hex()
    if alg != 'sha512' or len(digest) != 128:
        raise SystemExit('unexpected lock integrity: ' + key)
    src = cache / 'content-v2' / alg / digest[:2] / digest[2:4] / digest[4:]
    target = deps / 'tarballs' / (digest + '.tgz')
    if not src.is_file():
        incompatible = any(package.get(field) and platform not in package[field]
                           for field, platform in [('os','linux'), ('cpu','x64')])
        # npm also omits optional packages whose engines do not fit the pinned
        # toolchain. Match the previously verified local install in that case.
        if not (package.get('optional') and (incompatible or not (repo / key).exists())):
            raise SystemExit('missing cached tarball: ' + key)
    elif not target.exists():
        shutil.copyfile(src, target)
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, alg).hexdigest() != digest:
                raise SystemExit('bad cached tarball: ' + key)
        count += 1
    # Rewrite transport only in the dependency staging lock. Keep original integrity.
    package['resolved'] = 'file:/kit/deps/tarballs/' + target.name
(deps / 'package-lock.json').write_text(json.dumps(data))
native = {'better-sqlite3/build/Release/better_sqlite3.node': 'df9fbd0d061f360d81fb51e265c53c9605020bd68219e34f33c07c85de15719a',
          'node-pty/build/Release/pty.node': '9b33df633d1dbd6a7e4d4ae11adca31a7d475c01421698abc9fdb564ec729e78'}
for name, expected in native.items():
    src = repo / 'node_modules' / name
    if src.resolve() != src or hashlib.sha256(src.read_bytes()).hexdigest() != expected:
        raise SystemExit('native dependency needs review for this runner: ' + name)
    dst = deps / 'native' / name
    dst.parent.mkdir(parents=True)
    shutil.copyfile(src, dst)
print(f'{count} distinct verified tarballs, 2 pinned native addons')
