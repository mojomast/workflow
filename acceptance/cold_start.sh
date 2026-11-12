#!/usr/bin/env bash
# Cold-start acceptance test for mojomast/workflow + mojomast/bundlebees.
#
# Usage:
#   acceptance/cold_start.sh [OUT_DIR]
#
# Modes (ACCEPTANCE_MODE):
#   auto       (default) docker if it is usable, else a clean temp HOME + venv
#   docker     run inside a fresh python:3.12-slim container (needs docker)
#   local      clean temp HOME + venv on this machine
#
# Other env:
#   WORKFLOW_REPO / BUNDLEBEES_REPO   clone URLs (default: public GitHub repos)
#   WORKFLOW_REF  / BUNDLEBEES_REF    branch or tag to test (default: main)
#   WORKFLOW_SRC                      local path or URL to clone the workflow
#                                     repo from instead (CI uses the PR checkout;
#                                     still a fresh clone, local mode only)
#   ACCEPTANCE_ADAPTER                scripted (default, offline) or a real
#                                     bundlebees adapter name, e.g. launcher
#   ACCEPTANCE_ALLOW_UNSAFE_LOCAL=1   allow running without bubblewrap/firejail
#                                     (logged as an intervention)
#
# No API keys are needed. Network is used only to clone the two public repos
# and pip-install pytest. Every environment workaround is written to
# OUT_DIR/interventions.jsonl and OUT_DIR/REPORT.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-${PWD}/acceptance-out}"
MODE="${ACCEPTANCE_MODE:-auto}"
WORKFLOW_REPO="${WORKFLOW_REPO:-https://github.com/mojomast/workflow.git}"
BUNDLEBEES_REPO="${BUNDLEBEES_REPO:-https://github.com/mojomast/bundlebees.git}"
WORKFLOW_REF="${WORKFLOW_REF:-main}"
BUNDLEBEES_REF="${BUNDLEBEES_REF:-main}"
PRIOR="${ACCEPTANCE_PRIOR_INTERVENTIONS:-}"

note() { PRIOR="${PRIOR:+$PRIOR||}$1::$2"; }

if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "error: $OUT is not empty; choose a new output directory" >&2
  exit 2
fi
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

if [ "$MODE" = auto ]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then MODE=docker; else MODE=local; fi
fi

if [ "$MODE" = docker ]; then
  # bubblewrap needs user namespaces inside the container; --privileged is the
  # simplest portable way on a throwaway container and is logged as such.
  exec docker run --rm --privileged \
    -e WORKFLOW_REPO -e BUNDLEBEES_REPO -e WORKFLOW_REF -e BUNDLEBEES_REF \
    -e ACCEPTANCE_ADAPTER -e ACCEPTANCE_ALLOW_UNSAFE_LOCAL \
    -e ACCEPTANCE_PRIOR_INTERVENTIONS="${PRIOR:+$PRIOR||}docker run --privileged::bubblewrap needs user namespaces inside the container" \
    -e ACCEPTANCE_MODE=local -e ACCEPTANCE_IN_CONTAINER=1 \
    -v "$HERE/cold_start.sh:/acceptance/cold_start.sh:ro" \
    -v "$OUT:/out" python:3.12-slim bash -c '
      apt-get update -qq >/dev/null && apt-get install -y -qq git bubblewrap >/dev/null &&
      bash /acceptance/cold_start.sh /out/run'
fi

# ---- local mode: clean HOME, clean venv, fresh clones ----------------------
if [ -z "${ACCEPTANCE_IN_CONTAINER:-}" ]; then
  note "ran in a clean temp HOME + venv instead of a container" "docker not used (ACCEPTANCE_MODE=$MODE)"
fi
for tool in git python3; do
  command -v "$tool" >/dev/null || { echo "error: $tool is required" >&2; exit 2; }
done

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/workflow-cold-start-XXXXXX")"
export HOME="$SCRATCH/home"
mkdir -p "$HOME"
unset PYTHONPATH VIRTUAL_ENV PIP_CONFIG_FILE GIT_DIR GIT_WORK_TREE || true
export GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 PIP_DISABLE_PIP_VERSION_CHECK=1
git config --global user.name "Cold Start"
git config --global user.email "cold-start@example.invalid"
git config --global init.defaultBranch main

echo "== cloning public repos (fresh)"
if [ -n "${WORKFLOW_SRC:-}" ]; then
  git clone -q "$WORKFLOW_SRC" "$SCRATCH/src/workflow"
  WORKFLOW_REF="$(git -C "$SCRATCH/src/workflow" rev-parse HEAD) (from WORKFLOW_SRC)"
else
  git clone -q --depth 1 --branch "$WORKFLOW_REF" "$WORKFLOW_REPO" "$SCRATCH/src/workflow"
fi
git clone -q --depth 1 --branch "$BUNDLEBEES_REF" "$BUNDLEBEES_REPO" "$SCRATCH/src/bundlebees"

echo "== installing (venv + pytest)"
python3 -m venv "$SCRATCH/venv"
"$SCRATCH/venv/bin/python" -m pip install -q "pytest>=8,<9"

echo "== running acceptance harness"
set +e
ACCEPTANCE_PRIOR_INTERVENTIONS="$PRIOR" "$SCRATCH/venv/bin/python" "$SCRATCH/src/workflow/acceptance/harness.py" \
  --workflow "$SCRATCH/src/workflow" --bundlebees "$SCRATCH/src/bundlebees" --out "$OUT" 2>&1 | tee "$OUT/harness.log"
RC=${PIPESTATUS[0]}
set -e

"$SCRATCH/venv/bin/python" "$SCRATCH/src/workflow/acceptance/report.py" "$OUT" \
  --template "$SCRATCH/src/workflow/acceptance/REPORT_TEMPLATE.md" \
  --env "mode=$MODE" --env "python=$("$SCRATCH/venv/bin/python" -V 2>&1)" \
  --env "git=$(git --version)" --env "workflow_ref=$WORKFLOW_REF" --env "bundlebees_ref=$BUNDLEBEES_REF" \
  --env "os=$(uname -sr)" >/dev/null
echo "report: $OUT/REPORT.md"
rm -rf "$SCRATCH"
exit "$RC"
