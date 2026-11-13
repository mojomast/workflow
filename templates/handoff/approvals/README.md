# Approval markers

A file in this directory is a claim that a human-checked extra gate has passed (for example, that named blockers on a PR were verified on the current head).

- Write a marker only after a live check.
- Put in the file: the PR, the head SHA checked, what was verified, who checked it, and the date and time (with zone).
- Never put secrets in a marker.
- The merge-watch script should treat a missing marker as "do not merge."
