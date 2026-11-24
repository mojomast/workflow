# t1634 merge queue (coordinator tool)

`mergeq.py` is the merge-queue owner that the t1634 coordinator ran on the box. Each cycle it reads the host queue (`~/rizzstack-t1634/mergeq/queue.json`) and lands green, reviewed PRs. It never uses `--admin`, never force-pushes, and runs gitleaks before every push through `push.sh`.

- **B batching** (bundlebees, orbitdesktop): PRs with disjoint files merge in the same cycle. Batching turns off if main CI goes red.
- **D merge trains** (workflow, hyvv): these strict repos have no native queue, because GitHub merge queues need an organisation-owned repo. 2–5 green PRs are stacked at their verified heads on a `train/*` branch, CI runs once, and one merge lands them all. A train is dissolved on a CI failure, a member head moving, or main moving. A failed train switches to one PR at a time for 30 min.
- **E merge on CI completion:** `gh pr merge --auto --match-head-commit` is armed only when nothing has failed and every non-required check is already green. It is disarmed on a conflict, a failure or main going red.

Environment: `MERGEQ_HOST` (ssh target of the coordinator host, required), `MERGEQ_RUN` (state dir, default the cwd), `MERGEQ_PYTHON` (interpreter for the parity and bundle checks).
