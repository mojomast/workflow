# Quickstart: worker profile

A worker host only. hyvv serves the versioned /v1 attempts API and governed provisioning on its own
machine; a coordinator elsewhere sends work to it. Manifest:
[../../profiles/worker.json](../../profiles/worker.json).

## 1. Clone and run the suites

Commands from `contrib/bee-ci/jobs/hyvv.yaml` (the checked-in dispatch manifest for the hyvv repo):

```bash
git clone https://github.com/mojomast/hyvv
cd hyvv
uv sync --frozen --no-dev || uv sync --no-dev
uv run python -m unittest discover -s tests -v
uv run python -m contract -v
sh scripts/install.sh --dry-run
```

`uv run python -m contract` is the contract suite; the unit suite was 171 tests with 2 skipped at the
audited revision, the contract suite 93 with 3 skipped (chapter 23, §4).

## 2. Optional: release assets and the secret scan

```bash
rm -rf dist release-assets
uv build
uv run python scripts/build_release_assets.py --dist dist --out release-assets
test "$(ls dist | wc -l | tr -d " ")" = 2
```

The scan leg needs gitleaks on PATH:

```bash
gitleaks detect --source . --redact --verbose --exit-code 1
scripts/scan-secrets.sh
```

## 3. Point a coordinator at it

A coordinator (bundlebees, see the orchestrator profile) dispatches attempts to this host over the
/v1 API and provisions project workspaces through the governed provisioning endpoints (capabilities,
project, receipts, cleanup), authorized by the host-enrolled provisioning policy file — never by the
request. Workers dial out to a coordinator; nothing here opens an inbound port to the open internet
(chapter 14).

## What this profile cannot do

- Cannot dispatch, queue or accept work alone — something else must call /v1/attempts.
- Cannot run the coordinator, the reconciler or any verify suite.
- Governed provisioning lives on the pinned feat branch (PR 4 open at the audited revision), not on a
  merged mainline (gap G10).
- The Windows path is unit-tested but no live Windows host has run it.
- The parked-project refusal gate is a hyvv proposal, not shipped behaviour (gap G11).
