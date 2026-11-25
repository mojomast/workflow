#!/bin/bash
set -euo pipefail
export HOME=/tmp/check-home PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8
export NPM_CONFIG_OFFLINE=true NPM_CONFIG_CACHE=/tmp/check-home/.npm NPM_CONFIG_AUDIT=false NPM_CONFIG_FUND=false GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
mkdir -m 0700 -p "$HOME"
cp -R /kit/tools/usr/. /usr/
/usr/sbin/ldconfig
getent passwd sshd >/dev/null || /usr/sbin/useradd --system --no-create-home --home-dir /run/sshd --shell /usr/sbin/nologin sshd
mkdir -p -m 0755 /run/sshd
ln -s /usr/local/bin/python3 /usr/bin/python3
cp -R /kit/prefix/. /usr/local/
for b in node npm npx; do ln -s /usr/local/bin/$b /usr/bin/$b; done
cp -R /input /candidate
mkdir /deps
cd /deps
cp /kit/deps/package*.json .
npm ci --offline --ignore-scripts --no-audit --no-fund --include=dev
cp -R /kit/deps/native/. node_modules/
mv node_modules /candidate/node_modules
cd /candidate
node --version; npm --version; git --version; tmux -V; /usr/sbin/sshd -V; /usr/bin/python3 --version
git rev-parse HEAD
for h in a15d7eb947d0c5936ce7ac66b5cda0ce49b5fea3 ae14c4f327765dc5ff8786070dedc9eb7e9b3abe d35142f812619c1a2492f0223fce2798cf105b6d b404cf13e4a5a6aef197f7d12394648672061da2; do git archive "$h" >/dev/null; done
for f in b404cf13:src/plugins.ts 6db86bd:server/workbench-environments.mjs 5b31fdab:server/agent-profiles.mjs 5b31fdab:tests/agent-profiles.test.mjs; do git show "$f" >/dev/null; done
node -e "const db=new(require('better-sqlite3'))(':memory:'); console.log('SQLite',db.prepare('select sqlite_version() as v').get().v); require('node-pty'); console.log('Vite',require('vite/package.json').version,'TypeScript',require('typescript/package.json').version); require('esbuild').transformSync('const x=1');"
if [[ $1 == preflight ]]; then
  node scripts/generate-workspace-contract.mjs --check
  node --experimental-strip-types scripts/generate-workbench-contract.mjs --check
  node --experimental-strip-types --test --test-concurrency=1 tests/{persistent-terminal,ssh-sshd,workspace-schema12,workspace-store-preserve-schema}.test.mjs
  npm run test:irc
  exit
fi
[[ $1 == check ]]
start=$(date +%s%N)
date --utc +CHECK_STARTED=%FT%TZ
npm run check || rc=$?
date --utc +CHECK_ENDED=%FT%TZ
echo "CHECK_EXIT=${rc:-0} CHECK_DURATION_MS=$(( ($(date +%s%N)-start)/1000000 ))"
exit "${rc:-0}"
