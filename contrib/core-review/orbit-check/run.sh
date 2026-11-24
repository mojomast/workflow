#!/bin/bash
set -euo pipefail
umask 077
[[ $# == 4 && ( $1 == preflight || $1 == check ) ]] || { echo 'usage: bash run.sh preflight|check KIT ORBIT_REPO REVIEWED_PATH_LIST' >&2; exit 2; }
mode=$1; kit=$(realpath "$2"); repo=$(realpath "$3"); list=$(realpath "$4")
here=$(dirname "$(realpath "$0")")
image=sha256:78976a69c067520ef8be34cde307ef9f6fea6dcefa50edb57039773d241ca0db
test "$(cat "$kit/image-id")" = "$image"
docker image inspect "$image" >/dev/null
out=$(mktemp -d "$(realpath "${TMPDIR:-/var/tmp}")/orbit-check-run.XXXXXXXX")
echo "Evidence: $out"
trap 'rm -rf -- "$out/source"' EXIT
python3 "$here/snapshot.py" "$repo" "$list" "$out/source" |& tee "$out/snapshot.log"
test "$(sha256sum "$out/source/package-lock.json" | cut -d' ' -f1)" = "$(cat "$kit/deps/lock.sha256")" || { echo 'Lock changed; prepare and validate a fresh kit.' >&2; exit 1; }
docker run --rm --pull=never --network=none --init --pids-limit=640 --memory=6g --cpus=3 \
  --security-opt=no-new-privileges --mount "type=bind,source=$kit,target=/kit,readonly" \
  --mount "type=bind,source=$out/source,target=/input,readonly" \
  --mount "type=bind,source=$here/inside.sh,target=/runner.sh,readonly" \
  --entrypoint /bin/bash "$image" /runner.sh "$mode" |& tee "$out/$mode.log"
