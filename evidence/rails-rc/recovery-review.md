# Closing review: E3 notifier replay and E6 normal tick

**Both previously reported blockers are fixed on the exact Git heads below. No unresolved blocker found in these two paths.**

| Finding | Reviewed head | Disposition |
|---|---|---|
| **E3 — Hyvv notifier** | `35a4d0cf9473b3d30a2b8eb0b71ab9d10b6509a8` | Fresh delivery requires successful registration of the event's canonical digest. Replay requires an existing registration, verifies the retained data against its pinned position and digest, and sends the verified in-memory event without reopening the file. Divergent content is refused. See `launcher.py:894–921`, `landing_export.py:461–475,500–514,553–571`. |
| **E6 — BundleBees normal tick** | `be8cebb0ccd730a0ed82e940c15228708a6bef91` | Acceptance uses the sealed wave record, attempts, request digest and tested commit. The live result must match that record and ref. A prepared Git ref transaction holds the exact head through the signed job save; the normal tick neither repairs a missing ref nor does a second unlocked save. See `job_cli.py:419–425,546–571`, `job.py:1474–1507`, `integrate_job.py:378–392`, `reconcile.py:668–681`. |

**Independent restart checks.** On Hyvv, a fixture process exited immediately after the first file notification. Restart redelivered that same event and then the second pinned event; the index was byte-identical. Delivery is at least once. On BundleBees, separate fixture processes exited immediately **before** and **after** the signed acceptance save. In each case two subsequent ticks left one acceptance with the same wave, attempts, request digest and commit. Proof and receipt files were byte-identical, and integration did not run again.

**Results:** BundleBees **58 passed**, including missing ref, moved ref, different receipt, missing digest, and a competing ref writer at the save boundary. The missing-ref case returned `wave_reconciliation_required`, left the task verified, wrote no acceptance and did not recreate the ref. Hyvv **23 passed** (plus 4 subtests). **81 repository tests passed, zero failed or skipped; all 3 additional process-interruption checks passed.** [Local run logs](closing-recovery-evidence/logs/). Tests used extracted Git objects and disposable Linux fixtures. Process-restart results do not establish power-loss durability or merge approval.
