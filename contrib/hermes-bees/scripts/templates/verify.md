<!--
Reference implementation only. Windows-host reference template for one
checkout. Paths and host-specific values must be replaced with local values.
This tree includes no key files and is not an installer.
-->
# Template: verify (verify bee for a finished work bee; report-only)
Default follow-up for every succeeded work bee. The launcher (>= 0.1.11) seeds the project into a fresh
tree and uploads that bee's patch to $VERIFY_PATCH_FILE (brief field "verify_of"). The seeded base is
{{local_base_rev}} when the work result recorded it. The verify bee applies the patch to that seeded
tree, runs the work brief's commands plus a secret scan, and reports pass or fail. It never pushes; the
box coordinator pushes only after a pass plus its own secret scan.
Easiest: values.json = {"work_brief": "briefs/<WORK>.json", "verify_of": "att_..."}; render_brief.py fills the rest.
Slots: {{task_id}} {{title}} {{label}} {{repo_project}} {{branch}} {{source_rev}} {{local_base_rev}} {{verify_of}} {{work_task_id}} {{assigned_files}} {{work_commands}} {{work_acceptance}} {{timeout_s}} (default 2700) {{progress_file}}

```json
{
  "title": "{{title}}",
  "label": "{{label}}",
  "kind": "opencode",
  "role": "verify",
  "verify_of": "{{verify_of}}",
  "work_task_id": "{{work_task_id}}",
  "project": "{{repo_project}}",
  "branch": "{{branch}}",
  "source_rev": "{{source_rev}}",
  "deps": [],
  "model": "deepseek-v4.1-flash",
  "fallback_model": "deepseek-v4.1-flash",
  "tier": "deepseek-v4.1-flash",
  "budget": {"timeout_s": {{timeout_s}}, "max_tool_calls": 120},
  "assigned_files": {{assigned_files}},
  "deliverables": ["VERIFY.json verdict in the completion report (no file changes beyond the applied patch, except the required shots/ progress log, which is coordinator telemetry)"],
  "commands": {{work_commands}},
  "box_verify_commands": [],
  "acceptance": [
    "The work patch applies cleanly to the seeded base ({{local_base_rev}} if recorded, otherwise the tree the launcher already seeded) with `git apply --index --check` then `git apply --index`; if it doesn't, verdict=fail with the apply error tail.",
    "Every changed path is inside the brief's assigned_files. shots/ is coordinator telemetry, not patch content: the required progress log is allowed and ignored by verify. Any other path outside the lease is verdict=fail (scope_violation).",
    "Each work command was run exactly as written (wrapped in timeout), with rc and a short output tail recorded; any rc!=0 is verdict=fail.",
    "Secret scan of the applied diff and changed files: gitleaks if present, else a regex scan for private keys, bearer/API tokens, 32+ char token-like strings, IPs, tailnet names, /home, /workspace and C:\\Users paths, and the banned word from the HARD RULES Content line. Any hit is verdict=fail (report the file and rule, never the matched value).",
    "Work acceptance items that need a live endpoint or BBS token are listed under not_run, not passed.",
    "You changed no file yourself, created no commit, branch or tag, and pushed nothing."
  ],
  "return_format": "JSON: {\"task\":\"{{task_id}}\",\"role\":\"verify\",\"verify_of\":\"{{verify_of}}\",\"verdict\":\"pass|fail\",\"apply\":\"ok|failed\",\"scope\":{\"ok\":true,\"outside\":[]},\"commands\":[{\"cmd\":\"\",\"rc\":0,\"tail\":\"\"}],\"secret_scan\":{\"tool\":\"gitleaks|regex\",\"hits\":[{\"file\":\"\",\"rule\":\"\"}]},\"work_acceptance\":[{\"item\":\"\",\"pass\":true,\"evidence\":\"\"}],\"observed\":[],\"not_run\":[],\"open_issues\":[]}",
  "objective": "{{> _house-rules.md}}\n\nROLE: You are a VERIFY bee for work attempt {{verify_of}} (task {{work_task_id}}). You check another bee's work; you do not improve it. House-rule lines about working on {{branch}} starting from {{source_rev}} do not apply: the launcher has already seeded a fresh tree. Do not require HEAD to equal source_rev and do not require the current branch name to match the work branch.\n\nSTEPS:\n1. `git status --porcelain` must be empty. The seeded base is {{local_base_rev}} if recorded, otherwise the tree already in the workdir.\n2. `git apply --index --check \"$VERIFY_PATCH_FILE\"`, then `git apply --index \"$VERIFY_PATCH_FILE\"`. Never edit the patch or any file.\n3. `git diff --cached --name-only HEAD` and compare against assigned_files. Ignore shots/ and any PROGRESS.log: those are coordinator telemetry, not patch content, and do not count as a scope_violation.\n4. Run every command in commands, in order, each under `timeout` (default 900 s). Commands use python3, not python.\n5. Secret-scan the staged diff and changed files as the acceptance says; report file and rule only.\n6. Check each work acceptance item below against what you observed:\n{{work_acceptance}}\n\nverdict=pass only if apply, scope, every command and the secret scan all pass. Report-only: no fixes, no commits, no push. Return the JSON in return_format as worker_claims: you MUST include verdict (\"pass\"|\"fail\"), commands (array of {cmd, rc, tail}), and secret_scan ({tool, hits}) with hits=[] when clean."
}
```
