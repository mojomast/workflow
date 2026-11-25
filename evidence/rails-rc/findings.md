# Starting-tuple independent review ledger

The two reviewers inspected code and exercised disposable fixtures. Both recommended **hold**. Their findings apply to the exact heads in `start.json`. Implementer GREEN, verifier GREEN, review disposition, and owner decision are separate states. This ledger lists the starting findings; later run records supersede their status only when they identify the reviewed SHA and observed result.

| ID | Severity | PR / area | Starting observation | Required disposition |
|---|---|---|---|---|
| E1 | High | BB #82 native producer / W #91 R18 | Producer accepted a native RETURN refused by the frozen receiver. | Publish a generated native packet, exact SHA tuple, receiver check and negative substitution results. See [`before/`](before/) and [`native/`](native/). |
| E2 | High | BB #82 signed feedback | Admission and durable commit had different validity windows. | First write requires valid authority at commit; an expired replay may only recover an identical prior receipt. |
| E3 | High | H #26 landing export | Rediscovery could associate new content with an occupied durable position. | Pin canonical content, allow byte-formatting-only changes, refuse divergent replay without advancing. |
| E4 | High | BB #82 sidecar | A RED link could outstate native test evidence. | Require signed failing criterion at matching contract, intent and revision. Keep unverified observations available as observations. |
| E5 | High | O #46 evidence board | A positive label did not establish applicability to the selected head. | Bind current evidence to an explicit code revision; otherwise display historical/informational evidence. |
| E6 | High | BB #82 integration recovery | Recovered success did not require the same evidence as new success. | Require matching execution, attempts, commits and affirmative suite before success or promotion. Reconcile legacy state. |
| E7 | High | BB #82 review criteria | A recorded reviewer role did not prove independent review. | Never count an unverified identity or out-of-scope recorded review as an independent PASS. |
| E8 | High | BB #82 native verification | AC classification could outstate the suite result or task's participation in a wave. | Check exact task, candidate and affirmative check at consumption. |
| E9 | High | BB #82 dispatch attribution | Source integrity alone did not establish that a worker had been assigned the attempt. | Require independent coordinator evidence binding both dispatch and contract; default to informational or refuse. |
| E10 | Medium | BB #82 source diagnostics | Malformed input could leave private fingerprints in a shared diagnostic. | Omit unsanitized input digests; retain meaningful scoped errors. |
| E11 | Medium | H #26 journal / BB #82 RETURN publication | Process restart results did not establish durability across power loss or atomic multi-file publication. | Document and enforce acknowledgement boundaries, verify packet generation before use; do not claim untested storage guarantees. |
| E12 | Medium | BB #82 shared ledger; H #26 / O #46 vendors | Independent cold-start writers could fail during WAL initialization. | RED `277ac26`, GREEN `e176ec2`, manifest `b6f65d5`. Independent reviewer observed blocked and successful opens with a controlled lock; recheck both consumers. |
| E13 | High | BB #82 peer import | Refusing a contradictory remote checkpoint did not in itself mark the durable source unusable. | Halt the affected source, retain cursor/evidence, distinguish temporary outage. |

Additional integration findings: coinstalled Python packages need a versioned-runtime resolution check; BundleBees' earlier canonical pin label lacked a commit identity; the old benchmark conflated HTTP lookup with browser visibility; an ordinary single-repo Workflow unit run can skip missing siblings. Check the separate tuple runner, corrected workload, packaged wheels and commit-bound vendor parity. Record all CI failures against their actual job and HEAD, even if a local rerun passes.

**Scope:** Tripwires that passed on the starting tuple included isolated read credentials, absence of the production legacy approval mount, append/feedback separation, worker-join token rotation/revocation and byte parity at the existing pins. Worker joining is a scoped presence/integrity mechanism. A reported digest is not provisioning or independent attestation of a running worker. Independent agent review here does not count as an authorized GitHub or receiver approval.
