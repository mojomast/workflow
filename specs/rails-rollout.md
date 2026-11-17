# R18 local Rails acceptance and rollout gates

**The local transport and read slice works on the tested dirty trees. Product M1 and activation remain pending.** This exercise boots new loopback listeners and uses two disposable SQLite ledgers. No jobs, providers or live workspaces are contacted. The input [scenario](../schemas/rails/fixtures/m1-scenario.json) is a synthetic launcher JSONL fixture, not a recording from a deployed Windows worker. Compare [R00's native-trace finding](rails-feasibility.md) and the [milestone definitions](rizzstack-rails-spec.md#8-ux-and-acceptance-milestones).

## Reproduce

Run from `workflow` on Linux, with Python 3.10+, Git, Node >=22.12 on PATH and Orbit's already-installed native dependencies matching that Node ABI. By default the other three repositories are sibling checkouts named `hyvv`, `bundlebees`, `orbitdesktop`. `RAILS_R18_ROOT` can point at another local parent. No API base URLs are test settings. Missing sibling artifacts are named as skips in standalone Workflow CI; use required mode for a release check:

```sh
RAILS_R18_REQUIRED=1 python3 -m unittest discover -s tests -p test_rails_acceptance.py -v
```

For the browser check, set `RAILS_R18_BROWSER_DIST` to an isolated Orbit build from the same frontend source (use the destination reported by `npm run build` in Orbit) and `CHROMIUM_EXECUTABLE` to a local Chromium executable or `PLAYWRIGHT_BROWSERS_PATH` to an existing compatible installation. R18 runs the real owner shell from a temporary server root, unlocks it with an ephemeral credential, opens **Rizzstack Rails** in the command palette and selects the imported finish ID in the sandboxed inspector. It also checks that the parent shell acknowledges that selection. No browser download or request to another origin is needed. Without a build, `test_browser_inspector_and_cli_identity` explicitly skips; that run does not attest browser visibility.

Set `RAILS_R18_EVIDENCE_DIR` to a **new** directory under a private local scratch directory to keep the handoff; by default it is deleted with the test workspace. The run refuses to overwrite a previous handoff. Credentials and private server state are never included. Compare the four base heads **and** selected working-file digests in `run-provenance.json`; base commits alone do not identify these binaries. Workflow history records R00 #80, R01 #83, and the early adoption batch #87. Orbit #43–45 and BundleBees #70 are component history, not this integration result.

## What the check observes

1. The real launcher starts with `rails_enabled`, a peer allowlist and a dedicated read credential. Its idle built-in fake **execution backend** avoids loading Cua; there is no simulated launcher HTTP, worker ledger or exporter. Startup consumes the fixture journal. `GET /v1/rails/events` refuses unauthenticated readers. `GET /v1/rails/head` independently supplies the terminal anchor.
2. `RemoteRailSource.import_into` uses the real authenticated launcher transport; each pull is a new coordinator process. Stop the worker after the first commit, assert the failed pull preserves the committed cursor, append the completion to the source while offline, then restart on the same worker state. Resume from the ledger and deliberately replay from zero. The test checks original canonical bytes, contiguous sequence/hashes from genesis, exact call and event IDs, two distinct import receipts and zero new rows on replay. Coordinator queries never read a worker database or share a worker directory.
3. Coordinator `feedback.record` targets the imported finish ID; reopening and repeating the same quality click produces one durable feedback event and zero interventions. It is an automated writer check. The read-only deployment refuses mutation at both the R12 service and real Orbit owner proxy. No human rating, approved retry, or Hermes session mutation was observed.
4. `python3 -m contrib.rails_server` opens the coordinator ledger. `server/index.mjs` registers the fixed `/api/rizzstack/rails/` proxy; it injects a separate upstream read credential. The authenticated `events` result matches the JSON from `python3 -m bundlebees_plugin.rails_cli query` on that ledger. `view` contains one mark for each selected ID. Uncredentialed/cross-credential reads fail; reading does not change DB/WAL bytes. `partial` coverage is a valid read result.
5. The [RETURN sidecar](../schemas/rails/evidence.schema.json) is created from this run's identities, origin heads, committed checkpoint, observations, local revision, policy, gaps and intervention count. `result.json`, `view.json` and both canonical chain exports let a recipient resolve each selected ID after shutdown. Wrong worker/peer hash, truncation, wrong code/contract revision or a different selection fail the receiver check. Checkpoint agreement is not independent signing. A verifier link needs a real applicable run; this fixture has none. Decision: `pending`.

The generated `RETURN.md` links `rails-evidence.json` in its evidence table. A real authorized campaign must also put the relative sidecar path in the appropriate `rizzstack.return/1` `acceptance[].evidence` and preserve its pending decision object (see [§31.9](../docs/31-campaign-continuity.md#319-rails-return-contract)). The fixture does not invent the packet, approval, verification suite or transport receipt necessary to issue that manifest.

## Recorded evidence and limits

Local run on 2026-11-17, Python 3.13.5 / Node 22.19.0 / Chromium 152.0.7977.30 on Linux, against bases Workflow `58aa969`, hyvv `9bed649`, BundleBees `07cdc17`, Orbit `9cb894b` **plus working-tree edits**. All four R18 tests passed, no skips (22.882 s). Preserved scratch handoff `r18-inspected-local`:

| Observation | Recorded result |
|---|---|
| Worker range and peer checkpoint | Seq 1–4; both heads `580e6678426e787261c4d93590746575a6ea023ffbfd3cacafcc0bcb8ca65177` |
| Mark selected in Chromium and returned by the CLI | `m-54b34f5c2549-27584d68-affb-464d-934b-b82374b92638:3` (`tool.finish`) |
| Coordinator feedback | `m-6cabfd732a35-9ec00dd9-f743-416c-a88a-7029c227cab7:3`, one quality vote after duplicate submission; zero interventions |
| Read surfaces | Owner proxy and CLI returned the same five items; source coverage remained partial. Browser acknowledgment and build index digest are in `browser-selection.json`. |
| Schema checks | All four worker envelopes and three coordinator envelopes, including all kind-specific payloads, passed the frozen R01 schemas. RETURN sidecar validated, with an empty verifier-link list and pending decision. |

The two other worker rows are source checkpoints. These are observed values, not a golden fixture; each run generates its own UUIDs, timestamps and hashes.

**Why transport and schema checks are separate:** an earlier run (`r18-first-local`) transported R02 bytes intact, but those bytes had `lane` instead of the R01 lane fields, no envelope `dedupe_key`, sparse scope and a structured redaction policy. The producer/vendor change made during integration resolved the mismatch for the scenario above. Older ledgers and untested event kinds do not inherit this result. R18 now fails on an envelope or payload mismatch instead of re-authoring the imported bytes. During browser integration one run also timed out opening the command palette; the test now waits for the async unlock dialog to close before the shortcut.

**Unmeasured:** Windows journal locking/native installed version, a real bounded campaign, independent verifier/reviewer records, human feedback, owner action authorization, off-machine anchors, and M2 latency/soak targets. Component checks and fixture timing do not establish those properties.

## Promotion and rollback

Recheck the contract and vendor manifests at reviewed immutable heads. Stage worker export on an isolated Windows worker, then one coordinator import owner, then R12 and the authenticated Orbit read route. Check exact worker ID in both browser inspector and CLI after disconnect/restart; verify read-only paths and doctor installed/loaded parity. For M1 require actual dispatch/RED/GREEN/review/integration and human evidence at the correct revision before attaching the sidecar. For M2 exercise authorized retry, the specified 100k-event workload and the 30-minute reconnect run on recorded hardware. Activation requires owner approval and a current-head independent review. To roll back, disable the route/importer and revert the binaries/configuration; retain the ledger, source journals and anchored handoffs. Do not downgrade by deleting or rewriting history.
