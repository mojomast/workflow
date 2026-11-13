#!/usr/bin/env bash
# Fail-closed merge watch for already-approved PRs.
# Fill in the APPROVED list and run with DRY_RUN=1 until a dry-run log has been read.
# This is an example, not a ready-to-enable service.
#
# Gates (all required):
#   PR is OPEN (already-merged = skip)
#   not a draft
#   base is the intended branch
#   every check on the exact head concluded SUCCESS (no skipped/neutral/pending/queued)
#   merge state is clean
#   declared predecessor is already merged
#   at most one merge per run
#   merge names the head that was checked
#   never --admin or any bypass flag
#
# Extra markers (optional): a path that must exist in APPROVAL_DIR before that PR may merge.
set -uo pipefail

DRY_RUN="${DRY_RUN:-1}"
APPROVAL_DIR="${APPROVAL_DIR:-./approvals}"
# REPO:NUMBER:BASE:PREDECESSOR_REPO:PREDECESSOR_NUMBER:OPTIONAL_MARKER_FILE
# PREDECESSOR fields are "-" when there is none. MARKER is "-" when there is none.
APPROVED=(
  # "example/repo:12:main:-:-:-"
  # "example/repo:13:main:example/repo:12:13-blockers-verified"
)

merged_this_run=0

is_green() {
  # Reads gh --json statusCheckRollup on stdin / from a file path in $1.
  # Exit 0 only when the list is non-empty and every conclusion is SUCCESS.
  python3 - "$1" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
checks = data.get("statusCheckRollup") or []
if not checks:
    sys.exit(1)
for c in checks:
    conclusion = (c.get("conclusion") or c.get("state") or "").upper()
    status = (c.get("status") or "").upper()
    if status and status not in ("COMPLETED",):
        sys.exit(1)
    if conclusion != "SUCCESS":
        sys.exit(1)
sys.exit(0)
PY
}

echo "merge-watch DRY_RUN=${DRY_RUN}"
echo "This example prints the intended checks. Wire it to your forge CLI before enabling DRY_RUN=0."
for spec in "${APPROVED[@]}"; do
  IFS=':' read -r repo number base pred_repo pred_num marker <<<"$spec"
  echo "would inspect ${repo}#${number} (base ${base}, predecessor ${pred_repo}#${pred_num}, marker ${marker})"
  if [[ "$marker" != "-" && ! -e "${APPROVAL_DIR}/${marker}" ]]; then
    echo "  skip: marker ${marker} is missing (fail-closed)"
    continue
  fi
  if [[ "$merged_this_run" -ge 1 ]]; then
    echo "  skip: already merged one this run"
    continue
  fi
  # Implement: fetch PR JSON, reject drafts / wrong base / non-clean merge state,
  # require predecessor merged, require is_green on the exact head, then
  # (if DRY_RUN=0) merge with --match-head-commit and never --admin.
done
