#!/bin/bash
# Prepare the versioned inputs used by the offline Orbit runner. Prints kit path.
set -euo pipefail
umask 077
repo=$(realpath "${1:?usage: bash prepare.sh /path/to/orbitdesktop}")
here=$(dirname "$(realpath "$0")")
node=$(realpath "${ORBIT_NODE_BINARY:-$(command -v node)}")
npm_dir=$(realpath "${ORBIT_NPM_DIR:-$(dirname "$(dirname "$(realpath "$(command -v npm)")")")}")
cache=$(realpath "${ORBIT_NPM_CACACHE:-${npm_config_cache:-$HOME/.npm}/_cacache}")
tmux_deb=$(realpath "${ORBIT_TMUX_DEB:?Set ORBIT_TMUX_DEB to the local tmux_3.5a-3_amd64.deb}")
image=sha256:78976a69c067520ef8be34cde307ef9f6fea6dcefa50edb57039773d241ca0db
docker image inspect "$image" >/dev/null
kit=$(mktemp -d "$(realpath "${TMPDIR:-/var/tmp}")/orbit-check-kit.XXXXXXXX")
trap 's=$?; if ((s)); then rm -rf -- "$kit"; fi' EXIT
cd "$kit"
mkdir -p prefix/{bin,lib/node_modules} tools/usr/{bin,sbin,lib/openssh,lib/x86_64-linux-gnu,share/git-core} deps/{tarballs,native}
cp "$node" prefix/bin/node
echo '2f822d544601dfff107f57d945b649d15c5bf6302595735a6bd9cdc7ee9669bd  prefix/bin/node' | sha256sum -c - >&2
test -f "$npm_dir/bin/npm-cli.js"
cp -a --no-preserve=ownership "$npm_dir" prefix/lib/node_modules/npm
ln -s ../lib/node_modules/npm/bin/npm-cli.js prefix/bin/npm
ln -s ../lib/node_modules/npm/bin/npx-cli.js prefix/bin/npx
test "$(prefix/bin/node prefix/bin/npm -v)" = 10.8.2
cp "$tmux_deb" tmux.deb
echo 'e6b6aa51780044e2c4a0e618c33f832b70ec80caa30303e6c254a0c851b5af78  tmux.deb' | sha256sum -c - >&2
dpkg-deb --fsys-tarfile tmux.deb | tar -C tools --no-same-owner -xf - ./usr/bin/tmux
rm tmux.deb
cp /usr/bin/{ssh,ssh-keygen,ssh-keyscan,git,ps,pgrep,pkill,prlimit,patch,diff,which,unzip,jq,openssl,curl} tools/usr/bin/
cp -d /usr/bin/git-{receive-pack,upload-pack,upload-archive} tools/usr/bin/
cp /usr/sbin/sshd tools/usr/sbin/
cp /usr/lib/openssh/sshd-{session,auth} tools/usr/lib/openssh/
cp -R /usr/share/git-core/templates tools/usr/share/git-core/
cp -a --no-preserve=ownership /usr/lib/git-core tools/usr/lib/
for f in $(ldd tools/usr/bin/* tools/usr/sbin/sshd tools/usr/lib/openssh/sshd-* 2>/dev/null | awk '$2=="=>" && $3 ~ /^\//{print $3}' | sort -u); do
  case "$(basename "$f")" in libc.so.6|libm.so.6|libpthread.so.0|libdl.so.2|libresolv.so.2) continue;; esac
  cp -L "$f" tools/usr/lib/x86_64-linux-gnu/
done
python3 "$here/dependency-kit.py" "$repo" "$cache" >&2
echo "$image" >image-id
printf '%s\n' "$kit"
