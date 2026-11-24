# BundleBees sandbox CI triage (run 44183932448, job 134395425337)

**Final local full-suite result on a clean detached checkout of `b1fa75b4b0a80d48feec134386c96cc1775c5ab8`: 2530 passed, 16 skipped, 0 failures, 1 dependency deprecation warning in 505.30 seconds.** No deselections. JUnit `/var/tmp/bb-ci-e0CgbC/b1fa75b-full.xml` (SHA-256 `99b36178c3eb4f6ac5790b1e856fe3756d9a63ba7d8192a1728be753dc1aa671`); complete output and skip reasons `/var/tmp/bb-ci-e0CgbC/b1fa75b-full.log`. This is local non-root strong-sandbox verification, not a hosted check status.

Hosted input: `be8cebb0ccd730a0ed82e940c15228708a6bef91`, 11 failed / 2516 passed / 16 skipped. Lines refer to `ci-bb-be8cebb.log` alongside this file (SHA-256 `4808c95b8b4ee666bdc4bafab87f60b86106eca2de4b8a93dae2941a6e13bfcc`).

| # | Test (short name) | Failure line / reason | Owner and correction |
|---|---|---|---|
| 1 | CrashRecoveryTwoFeatures: control | 509: integrated `job_a`, `AC-001: UNVERIFIED` at RETURN | Native producer, signed GREEN |
| 2 | CrashRecoveryTwoFeatures: crash A (dispatch) | 582: dispatch recovery completed; same uncovered `job_a` criterion | Native producer, signed GREEN |
| 3 | CrashRecoveryTwoFeatures: crash B (wave persisted) | 622: existing claim reported as missing its job. The passive existence lookup attempted recovery before the integration ref had been published. The active tick could not distinguish an interrupted first publish from deletion after publish. | Queue/integration recovery, one-shot pending publish below |
| 4 | CrashRecoveryTwoFeatures: crash C (mirror publish) | 702: mirror recovery completed; `job_a` lacked criterion GREEN | Native producer, signed GREEN |
| 5 | FactoryDriverCliReturn: real tick/provision | 788: contracted `job_c` accepted; no `AC-001` PASS at RETURN | Native producer, signed GREEN |
| 6 | FactoryDriverReturn: queue to validated return | 862: same uncovered criterion, `job_c` | Native producer, signed GREEN |
| 7 | TwoIndependentFeaturesThroughDriver: both progress | 928: RETURN for `job_c` lacked criterion GREEN | Native producer, signed GREEN |
| 8 | test_m43_wakeup_e2e / imported M4Dogfood: one authorised objective | 1042: corrected `job_m4_dogfood` reached RETURN with two uncovered task-local `AC-001` rows | Native producer, signed GREEN |
| 9 | M43WakeupDeterministic: failed attempt wakes consumer | 1097: distinct deterministic wakeup scenario reached same two uncovered rows | Native producer, signed GREEN |
| 10 | test_m4_dogfood_e2e / M4Dogfood: one authorised objective | 1211: same M4 test body as #8 collected under its defining module; same two uncovered rows | Native producer, signed GREEN |
| 11 | TwoFeaturesPacketNative: A/B verified history | 1272: `job_a` lacked criterion GREEN at RETURN | Native producer, signed GREEN |

The ten RETURN failures share the same contract: the factory had a verified commit and passing suite but no signed test-by-test GREEN for the candidate. Producer owner corrected the contracted verifier at `399bf918cbb5b3a9223c4597b587cb34f55de18c`.

Recovery correction **`b1fa75b4b0a80d48feec134386c96cc1775c5ab8`**, child of `399bf91`: the queue checks for the sealed job without adopting it and distinguishes absence from corruption. Fresh job integration stages a local pending Git ref bound to the sealed request/result. After rechecking the proof, one Git transaction checks the exact predecessor, publishes the tested head, and consumes that intent. The live tick still refuses a missing/moved published ref; recovery cannot repeat an already consumed automatic repair. Acceptance still holds the verify-only ref lock through job save. No migration, schema changes, remote action or overwrite of history. Coverage includes a real process crash before publication and a second tick after a real post-publication deletion.

**Local evidence** under `/var/tmp/bb-ci-e0CgbC`: `eleven.xml`: 16 passed, zero skipped (all 11 hosted IDs plus five related E2Es). `queue-fixed.xml`: 27 passed. The queue unit harness needed to accept the real `recover=False` keyword; no E2E outcome was mocked or expectation relaxed. Real UID 1000 in a disposable user/mount namespace; Debian package bubblewrap 0.12.0; plugin auto backend `bwrap`; real gitleaks 8.21.2; Workflow `9c69d3a987ea9544a77cdd9b5a259904eb36f006` and Hyvv `8ffaf73000974e0ba273c72fca42e07b79c38106` with REQUIRE flags enabled. The CI-compatible runtime is CPython 3.12.13, pytest 8.4.2. A preliminary CPython 3.13/pytest 9 run is not qualification: the M4 invalid-selector fixture did not produce its injected rejection with that out-of-range pytest version. No harness bypass was used to make it pass.
