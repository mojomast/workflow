# Evidence provenance

Every file below: source path on the coordinator host (moltussy-1), the command that
produced the packaged copy, and its validation status. Verify with
`sha256sum -c MANIFEST.sha256` against Git blob bytes (not Windows-converted checkouts).

| File | Source | Command | Validation |
|---|---|---|---|
| logs/att_*.log (7) | launcher host via forced-command SSH gateway | `ssh brrrrrrrr-launcher-admin logs <attempt-id> 80` (or 200 for att_0810b361) | captured verbatim; launcher redacts secret-shaped values itself |
| logs/att_f2ca4416d9674a19.log | same | same, lines=80 | 386 bytes; shows fetch failure `not our ref` (sha redacted by launcher) |
| logs/attempts-dump.json | coordinator host plugin state dir | `hermes bundlebees attempts --state-dir ~/.hermes/plugin-data/bundlebees > attempts-dump.json` | JSON-parse verified, 296 rows; coordinator states only - NOT launcher lifetime totals; no cancelled rows |
| logs/audit-tail.jsonl | `~/.hermes/plugin-data/bundlebees/audit.jsonl` | `tail -40 audit.jsonl` | JSONL; tail only |
| logs/outbox-events.tar.gz | `~/.hermes/plugin-data/bundlebees/events/outbox/` | `tar -C ~/.hermes/plugin-data/bundlebees/events -czf outbox-events.tar.gz outbox` | member count verified = 8 events + dir entry; ALL events dated 2026-11-14 19:32-19:55 EST |
| logs/scope-violation-att_ab4f1be9.json | `~/.hermes/plugin-data/bundlebees/verify-results/att_ab4f1be94f0e4609.json` | file copy | JSON-parse verified; see CORRECTION 2 item 2 for its evidentiary limits |
| logs/att_ef6953fe272341f9.json | `~/.hermes/plugin-data/bundlebees/verify-results/att_ef6953fe272341f9.json` | file copy | JSON-parse verified |
| leases/att_*.json (13) | `~/.hermes/plugin-data/bundlebees/leases/` | file copy | immutable lease records; `brief` field embeds the full brief text (F1 verification path) |
| records/*.md (2) | `~/.hermes/plugin-data/bundlebees/campaigns/` | file copy | the authoritative campaign ledger |
