<#
Reference implementation only. This is Windows/PowerShell reference code for one host. Paths and host-specific values in a live checkout must be replaced with local values. This tree includes no key files and is not an installer. Not the PC launcher (that remains a private tree; see the README).

bees.ps1 - the one small link between the box coordinator and the PC beekeeper.
  bees.ps1 status [<card>]            compact JSON: gateway/cron/launcher view, or one card + its attempts (under 1 KB)
  bees.ps1 handoff <brief.json> [-DryRun]   validate a brief and create a beekeeper kanban card (idempotent on task_id)
  bees.ps1 result <card> [-Full] [-OutFile <path>]   compact verdict summary (no 1 KB cap); -Full prints full JSON after it, -OutFile writes full JSON
  bees.ps1 settle <card>              idempotent lifecycle: pass -> unblock if needed, then request-review; fail -> keep/move blocked
No tokens, hosts, IPs, URLs or C:\Users paths. Never dispatches a bee directly, never pushes, cancels or restarts anything.
#>
param([Parameter(Position=0)][string]$Verb = "status", [Parameter(Position=1)][string]$Arg = "", [switch]$DryRun, [switch]$Full, [string]$OutFile = "")
$ErrorActionPreference = "Stop"
$env:HERMES_NONINTERACTIVE = "1"
$H = Join-Path $env:LOCALAPPDATA "hermes\bin\hermes.exe"
$ATT = if ($env:BEES_ATT_DIR) { $env:BEES_ATT_DIR } else { Join-Path $env:USERPROFILE ".orbit-launcher\attempts" }
$PROTECTED = @("main","master","hermes/v0","hermes/art","hermes/art-nous","feat/improvements")

function Scrub([string]$s) {
  if (-not $s) { return $s }
  $s = $s -replace '(?i)[A-Z]:\\Users\\[^\s"''`]*', '<path>' -replace '(?i)/(home|workspace|tmp)/[^\s"''`]*', '<path>'
  $s = $s -replace '(?i)https?://[^\s"''`]+', '<url>' -replace '\b\d{1,3}(\.\d{1,3}){3}\b', '<ip>'
  $s = $s -replace '[A-Za-z0-9_\-]{32,}', '<redacted>' -replace '(?i)t\W*u\W*r\W*b\W*o\W*f\W*i\W*t', '<word>'
  return $s
}
function Out-Json($o) {
  $s = Scrub ($o | ConvertTo-Json -Compress -Depth 6)
  if ($s.Length -gt 1000) { $s = (@{ ok = $o.ok; truncated = $true; note = "reply over 1 KB; use 'result' or 'status <card>'" } | ConvertTo-Json -Compress) }
  Write-Output $s
}
function Hj([string[]]$a) { $r = '' | & $H @a 2>$null; if ($LASTEXITCODE -ne 0) { throw "hermes $($a[0]) $($a[1]) failed" }; return ($r -join "`n") | ConvertFrom-Json }
function AttemptInfo([string]$aid) {
  $p = Join-Path $ATT "$aid.json"
  if (-not (Test-Path $p)) { return @{ id = $aid; state = "unknown" } }
  $a = Get-Content $p -Raw | ConvertFrom-Json
  $ev = Join-Path $ATT "$aid.events.jsonl"
  $t = if (Test-Path $ev) { (Get-Item $ev).LastWriteTime } else { (Get-Item $p).LastWriteTime }
  return @{ id = $aid; state = $a.state; quiet_min = [int]((Get-Date) - $t).TotalMinutes }
}
function NormPath([string]$p) { if (-not $p) { return "" }; return ([string]$p).Replace([char]0x5C, [char]0x2F).TrimStart('./') }
function IsTelemetryPath([string]$p) {
  $n = NormPath $p
  return [bool]($n -match '(^|/)shots/' -or $n -match '(^|/)PROGRESS\.log$')
}
function PatchMap($r) {
  $m = @{}
  if ($r -and $r.patch -and $r.patch.files) {
    foreach ($f in @($r.patch.files)) {
      $p = NormPath $f.path
      if ($p) { $m[$p] = [string]$f.sha256 }
    }
  }
  return $m
}
function FileLease($workResult, $workAtt, $verifyAtt) {
  # Lease = assigned_files, plus work-patch paths already leased (in_assigned_scope). If assigned_files is empty, the work patch is the lease.
  $assigned = @()
  if ($workAtt -and $workAtt.brief -and $workAtt.brief.assigned_files) { $assigned = @($workAtt.brief.assigned_files | ForEach-Object { NormPath $_ } | Where-Object { $_ }) }
  if (($assigned.Count -eq 0) -and $verifyAtt -and $verifyAtt.brief -and $verifyAtt.brief.assigned_files) { $assigned = @($verifyAtt.brief.assigned_files | ForEach-Object { NormPath $_ } | Where-Object { $_ }) }
  $lease = @{}
  foreach ($p in $assigned) { $lease[$p] = $true }
  $wm = PatchMap $workResult
  if ($assigned.Count -eq 0) { foreach ($p in $wm.Keys) { $lease[$p] = $true } }
  elseif ($workResult -and $workResult.patch -and $workResult.patch.files) {
    foreach ($f in @($workResult.patch.files)) {
      $p = NormPath $f.path
      if (-not $p) { continue }
      if ($lease.ContainsKey($p) -or $f.in_assigned_scope -eq $true -or [string]$f.in_assigned_scope -eq "true") { $lease[$p] = $true }
    }
  }
  return $lease
}
function VerifyFor([string[]]$work) {
  # Newest verify bee whose brief.verify_of names one of this card's work attempts. Verdict is the verify bee's report,
  # cross-checked against launcher-observed data: it must have succeeded, leased sha256s must match the work patch
  # (patch_matches_work), and non-telemetry paths outside the lease are scope_violation (distinct from a content mismatch).
  # shots/** and **/PROGRESS.log are telemetry_extras (warning only).
  if (-not $work) { return $null }
  $v = Get-ChildItem $ATT -Filter "att_*.json" -EA SilentlyContinue | Where-Object { $_.Name -match '^att_[0-9a-f]+\.json$' -and $_.LastWriteTime -gt (Get-Date).AddDays(-7) } |
    Sort-Object LastWriteTime -Descending | ForEach-Object { $j = Get-Content $_.FullName -Raw | ConvertFrom-Json; if ($j.brief.verify_of -and ($work -contains $j.brief.verify_of)) { $j } } | Select-Object -First 1
  if (-not $v) { return @{ verdict = "none"; note = "no verify bee yet" } }
  $o = @{ attempt = $v.attempt_id; verify_of = $v.brief.verify_of; state = $v.state; verdict = "pending" }
  $rf = Join-Path $ATT "$($v.attempt_id).result.json"; $wf = Join-Path $ATT "$($v.brief.verify_of).result.json"
  if ($v.state -in @("failed","cancelled")) { $o.verdict = "fail"; $o.note = "verify bee $($v.state)" }
  elseif ($v.state -eq "succeeded" -and (Test-Path $rf)) {
    $r = Get-Content $rf -Raw | ConvertFrom-Json; $c = $r.worker_claims
    if (-not $c) { $c = [pscustomobject]@{} }
    # Shape A: verdict + commands[{cmd,rc,tail}] + secret_scan.hits
    # Shape B: checks[{name,command,passed}] (secret_scan may be a check name)
    $o.claimed = [string]$c.verdict
    if (-not $o.claimed -and $c.checks) {
      $fail = @($c.checks | Where-Object { -not ($_.passed -eq $true -or [string]$_.passed -eq "true") })
      $o.claimed = if ($fail.Count -eq 0) { "pass" } else { "fail" }
      $o.claimed_from = "checks"
    } else { $o.claimed_from = "verdict" }
    $o.patch_matches_work = $false
    $o.telemetry_extras = @()
    $o.scope_violation = $false
    $o.scope_extras = @()
    $o.mismatch = @()
    if (Test-Path $wf) {
      $wr = Get-Content $wf -Raw | ConvertFrom-Json
      $wAtt = $null
      $wAttPath = Join-Path $ATT "$($v.brief.verify_of).json"
      if (Test-Path $wAttPath) { $wAtt = Get-Content $wAttPath -Raw | ConvertFrom-Json }
      $wm = PatchMap $wr
      $vm = PatchMap $r
      $lease = FileLease $wr $wAtt $v
      $mismatch = @()
      foreach ($p in @($lease.Keys)) {
        $inW = $wm.ContainsKey($p); $inV = $vm.ContainsKey($p)
        if (-not $inW -and -not $inV) { continue }
        $sw = if ($inW) { [string]$wm[$p] } else { "" }
        $sv = if ($inV) { [string]$vm[$p] } else { "" }
        if ($sw -ne $sv) { $mismatch += $p }
      }
      $tel = @(); $scope = @()
      $all = @(@($wm.Keys) + @($vm.Keys) | Select-Object -Unique)
      foreach ($p in $all) {
        if ($lease.ContainsKey($p)) { continue }
        if (IsTelemetryPath $p) { $tel += $p } else { $scope += $p }
      }
      $o.patch_matches_work = ($mismatch.Count -eq 0)
      $o.mismatch = @($mismatch | Sort-Object)
      $o.telemetry_extras = @($tel | Sort-Object)
      $o.scope_extras = @($scope | Sort-Object)
      $o.scope_violation = ($scope.Count -gt 0)
    }
    $cmds = @($c.commands)
    if ((-not $c.commands) -and $c.checks) {
      $cmds = @($c.checks | ForEach-Object { $ok = ($_.passed -eq $true -or [string]$_.passed -eq "true"); [pscustomobject]@{ cmd = [string]($_.command -or $_.name); rc = $(if ($ok) { 0 } else { 1 }) } })
    }
    $o.failed_cmds = @($cmds | Where-Object { $_.rc -ne 0 }).Count
    if ($c.secret_scan -and $null -ne $c.secret_scan.hits) { $o.secret_hits = @($c.secret_scan.hits).Count }
    elseif ($c.checks) {
      $ss = @($c.checks | Where-Object { [string]$_.name -match "secret[_-]?scan" } | Select-Object -First 1)
      $o.secret_hits = if ($ss) { if ($ss.passed -eq $true -or [string]$ss.passed -eq "true") { 0 } else { 1 } } else { -1 }
    } else { $o.secret_hits = -1 }  # -1 = no scan reported (fails)
    $o.not_run = @($c.not_run | Where-Object { $_ }).Count
    $o.verdict = if ($o.claimed -eq "pass" -and $o.patch_matches_work -and -not $o.scope_violation -and $o.failed_cmds -eq 0 -and $o.secret_hits -eq 0) { "pass" } else { "fail" }
  }
  return $o
}
function AttemptTokens([string]$aid) {
  $rf = Join-Path $ATT "$aid.result.json"
  if (-not (Test-Path $rf)) { return $null }
  $r = Get-Content $rf -Raw | ConvertFrom-Json
  $u = $null; if ($r.observed -and $r.observed.usage) { $u = $r.observed.usage }
  if ($u -is [string]) { try { $u = $u | ConvertFrom-Json } catch { return $null } }
  if (-not $u) { return $null }
  $o = @{}
  foreach ($k in @("cachedReadTokens","inputTokens","outputTokens","thoughtTokens","totalTokens")) {
    if ($null -ne $u.$k) { $o[$k] = $u.$k }
  }
  if ($o.Count -eq 0) { return $null }
  return $o
}
function ResultSummary($card, $status, $v, $workIds, $verifyId) {
  $tokens = @{}
  foreach ($wid in @($workIds)) {
    $t = AttemptTokens $wid
    if ($t) { $tokens.work = $t; break }
  }
  if ($verifyId) {
    $t = AttemptTokens $verifyId
    if ($t) { $tokens.verify = $t }
  }
  $tel = @(); if ($v -and $v.telemetry_extras) { $tel = @($v.telemetry_extras) }
  return @{
    card = $card
    status = $status
    verdict = $(if ($v) { $v.verdict } else { $null })
    claimed = $(if ($v) { $v.claimed } else { $null })
    patch_matches_work = $(if ($v) { $v.patch_matches_work } else { $null })
    scope_violation = $(if ($v) { $v.scope_violation } else { $null })
    secret_hits = $(if ($v) { $v.secret_hits } else { $null })
    failed_cmds = $(if ($v) { $v.failed_cmds } else { $null })
    telemetry_extras = $tel
    tokens = $tokens
  }
}
function SettlePlan([string]$status, [string]$blockKind, [string]$verdict) {
  # Pure plan: no hermes calls. Idempotent. pass -> review; fail -> blocked; else no-op.
  $st = [string]$status; $kind = [string]$blockKind; $v = [string]$verdict
  if ($v -eq "pass") {
    if ($st -in @("review","done")) { return @{ action = "noop"; status = $st } }
    $unblock = ($st -in @("blocked","scheduled") -or $kind -eq "needs_input")
    return @{ action = "review"; unblock = [bool]$unblock; force = ($st -eq "running") }
  }
  if ($v -eq "fail") {
    if ($st -eq "blocked") { return @{ action = "noop"; status = "blocked" } }
    return @{ action = "block" }
  }
  return @{ action = "noop"; status = $st; note = "no terminal verdict" }
}
function SettleCard([string]$card, $verify) {
  # Execute SettlePlan against the live board. Idempotent. Never touches other cards.
  $s = Hj @("kanban","show",$card,"--json")
  $status = [string]$s.task.status
  $kind = [string]$s.task.block_kind
  $plan = SettlePlan $status $kind $(if ($verify) { [string]$verify.verdict } else { "" })
  $out = @{ ok = $true; settled = $false; status = $status; action = $plan.action; verdict = $(if ($verify) { $verify.verdict } else { $null }) }
  if ($plan.action -eq "noop") { $out.note = $plan.note; if ($plan.status) { $out.status = $plan.status }; return $out }
  $actions = @()
  if ($plan.action -eq "review") {
    if ($plan.unblock) {
      $null = Hj @("kanban","unblock",$card,"--reason","verify pass; resume to record verdict")
      $actions += "unblocked"
    }
    $sum = "verified by bee, ready for the box to secret-scan and push"
    try {
      $args = @("kanban","request-review",$card,"--summary",$sum)
      if ($plan.force) { $args += "--force" }
      $null = Hj $args
      $actions += "request-review"
    } catch {
      $null = Hj @("kanban","request-review",$card,"--summary",$sum,"--force")
      $actions += "request-review-force"
    }
    $out.settled = $true; $out.status = "review"; $out.actions = $actions
    return $out
  }
  if ($plan.action -eq "block") {
    $reason = "verify fail claimed=$($verify.claimed) patch_matches=$($verify.patch_matches_work) scope_violation=$($verify.scope_violation) secret_hits=$($verify.secret_hits) failed_cmds=$($verify.failed_cmds)"
    $null = Hj @("kanban","block","--kind","needs_input",$card,$reason)
    $out.settled = $true; $out.status = "blocked"; $out.actions = @("blocked")
    return $out
  }
  return $out
}
function Emit-Result($compactObj, $fullObj) {
  # Always print the compact summary first, with no 1 KB cap. Optional full JSON after, or to -OutFile.
  # Parameter names must not collide with the script-level -Full switch (simple functions share script scope).
  $c = Scrub ($compactObj | ConvertTo-Json -Compress -Depth 8)
  Write-Output $c
  $fjson = Scrub ($fullObj | ConvertTo-Json -Compress -Depth 8)
  if ($OutFile) { [IO.File]::WriteAllText($OutFile, $fjson) }
  if ($Full.IsPresent) { Write-Output $fjson }
}

function LineTimestamp([string]$line) {
  # Parse a log line's own timestamp; $null if none. Never prints the line.
  # Local "YYYY-MM-DD[ T]HH:MM:SS"; a trailing Z or offset is converted to local time.
  if ($line -notmatch '(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?') { return $null }
  $local = [datetime]::ParseExact(($Matches[1] + " " + $Matches[2]), "yyyy-MM-dd HH:mm:ss", [cultureinfo]::InvariantCulture)
  $suf = $Matches[3]
  if (-not $suf) { return $local }
  if ($suf -eq "Z") { return [datetime]::SpecifyKind($local, [datetimekind]::Utc).ToLocalTime() }
  if ($suf -match '^([+-])(\d{2}):?(\d{2})$') {
    $sign = if ($Matches[1] -eq "-") { -1 } else { 1 }
    $off = [timespan]::FromMinutes($sign * (60 * [int]$Matches[2] + [int]$Matches[3]))
    return [datetime]::SpecifyKind($local, [datetimekind]::Utc).Add(-$off).ToLocalTime()
  }
  return $local
}
function MonthlyLimitSince([datetime]$since) {
  # Fail-fast: a monthly usage-limit 429 whose own log-line timestamp is on or after $since.
  # File mtime is only a cheap skip. Lines with no timestamp are ignored. Never prints the log.
  $hit = $false
  foreach ($rel in @("profiles\beekeeper\logs\errors.log", "profiles\beekeeper\logs\agent.log")) {
    $lp = Join-Path $env:LOCALAPPDATA (Join-Path "hermes" $rel)
    if (-not (Test-Path $lp)) { continue }
    if ((Get-Item $lp).LastWriteTime -lt $since) { continue }
    $lines = Get-Content $lp -Tail 200 -EA SilentlyContinue
    foreach ($line in @($lines)) {
      if ($line -notmatch "429|GoUsageLimitError|usage limit reached|UsageLimit") { continue }
      if ($line -notmatch "monthly|limitName") { continue }
      $ts = LineTimestamp $line
      if ($null -eq $ts) { continue }
      if ($ts -ge $since) { $hit = $true; break }
    }
    if ($hit) { break }
  }
  return $hit
}
function CardAttempts($show) {
  $txt = (@($show.task.body, $show.task.result, $show.latest_summary) + @($show.comments | ForEach-Object { $_.body })) -join " "
  return @([regex]::Matches($txt, 'att_[0-9a-f]{16}') | ForEach-Object { $_.Value } | Select-Object -Unique -Last 4)
}

try {
  switch ($Verb) {
    "status" {
      if ($Arg) {
        $s = Hj @("kanban","show",$Arg,"--json")
        Out-Json @{ ok = $true; card = $s.task.id; status = $s.task.status; assignee = $s.task.assignee; attempts = @(CardAttempts $s | ForEach-Object { AttemptInfo $_ }); comments = @($s.comments).Count }
      } else {
        $gw = ('' | & $H gateway status 2>$null) -join " "
        $cards = @(Hj @("kanban","list","--assignee","beekeeper","--json"))
        $by = @{}; foreach ($c in $cards) { foreach ($x in @($c)) { if ($x -and $x.status) { $by[[string]$x.status] = 1 + [int]$by[[string]$x.status] } } }
        $running = @(Get-ChildItem $ATT -Filter "att_*.json" -EA SilentlyContinue | Where-Object { $_.Name -match "^att_[0-9a-f]+\.json$" -and $_.LastWriteTime -gt (Get-Date).AddDays(-2) } | ForEach-Object { (Get-Content $_.FullName -Raw | ConvertFrom-Json).state } | Where-Object { $_ -notin @("succeeded","failed","cancelled") }).Count
        $memo = Join-Path $env:LOCALAPPDATA "hermes\scripts\bee-watch.state.json"
        $wage = if (Test-Path $memo) { [int]((Get-Date) - (Get-Item $memo).LastWriteTime).TotalSeconds } else { -1 }
        Out-Json @{ ok = $true; gateway = [bool]($gw -match "running"); beekeeper_cards = $by; launcher_active_attempts = $running; bee_watch_last_s = $wage; c_free_gb = [math]::Round((Get-PSDrive C).Free / 1GB, 1) }
      }
    }
    "handoff" {
      if (-not $Arg -or -not (Test-Path $Arg)) { throw "brief file not found" }
      $raw = Get-Content $Arg -Raw
      $b = $raw | ConvertFrom-Json
      $errs = @()
      foreach ($k in "task_id","objective","project","branch","source_rev") { if (-not $b.$k) { $errs += "missing $k" } }
      if ($b.source_rev -and $b.source_rev -notmatch '^[0-9a-f]{40}$') { $errs += "source_rev must be a 40-char sha" }
      if (-not $b.assigned_files -or @($b.assigned_files).Count -eq 0) { $errs += "assigned_files empty" }
      if (-not $b.acceptance) { $errs += "missing acceptance" }
      if ($b.branch -and ($PROTECTED -contains $b.branch -or $b.branch -match '^(release|integration)/')) { $errs += "protected branch" }
      if ($b.task_id -and $b.task_id -notmatch '^[A-Za-z0-9_.:-]{3,64}$') { $errs += "bad task_id" }
      $chk = $raw -replace '\b[0-9a-f]{40}\b', 'SHA'; if ((Scrub $chk) -ne $chk) { $errs += "brief contains a path, url, ip, token-like string or banned word" }
      if ($errs.Count) { Out-Json @{ ok = $false; errors = $errs }; exit 2 }
      $obj = [string]$b.objective; $title = "bee: $($b.task_id) " + $obj.Substring(0, [Math]::Min(60, $obj.Length))
      $body = "Dispatch this leased brief with bundlebees_dispatch (model deepseek-v4.1-flash), comment the attempt id here, then end your turn. Do not kanban_block or park this card as needs_input while a bee is running; that mid-run park sticks the card. bee-watch wakes you when it finishes; then dispatch the default verify bee (make-verify-brief.py). If the leased brief has verify_priority, run make-verify-brief.py <attempt> --priority <that value> so the verify bee uses that route. When verify finishes, run bees.ps1 result <card> (it settles: pass -> unblock if needed then request-review; fail -> blocked). Never push, merge, tag or deploy.`n``````json`n$raw`n``````"
      if ($DryRun) { Out-Json @{ ok = $true; dry_run = $true; would_create = @{ title = $title; assignee = "beekeeper"; idempotency_key = $b.task_id; max_runtime = "25m"; max_retries = 1; body_bytes = $body.Length }; would_dispatch = "hermes -p beekeeper kanban dispatch --max 1" }; break }
      $tmp = [IO.Path]::GetTempFileName(); [IO.File]::WriteAllText($tmp, $body)
      try { $c = Hj @("kanban","create",$title,"--body-file",$tmp,"--assignee","beekeeper","--idempotency-key",$b.task_id,"--max-runtime","25m","--max-retries","1","--skill","bundlebees:bundlebees-operator","--created-by","box-coordinator","--json") } finally { Remove-Item $tmp -EA SilentlyContinue }
      $t0 = Get-Date
      $disp = $null
      try { $disp = Hj @("-p","beekeeper","kanban","dispatch","--max","1","--json") } catch { $disp = @{ error = (Scrub $_.Exception.Message) } }
      Start-Sleep 8
      $limit = MonthlyLimitSince $t0
      $spawned = @()
      if ($disp -and $disp.spawned) { $spawned = @($disp.spawned | ForEach-Object { $_.task_id }) }
      $out = @{ ok = $true; card = $c.id; status = $c.status; dispatched = [bool]$spawned; spawned = $spawned; max_runtime = "25m" }
      if ($disp -and $disp.error) { $out.dispatch_error = $disp.error }
      if ($limit) { $out.ok = $false; $out.error = "monthly usage-limit 429 right after dispatch; fail-fast, not waiting out max-runtime" }
      Out-Json $out
      if ($limit) { exit 2 }
    }
    "result" {
      if (-not $Arg) { throw "card id required" }
      $s = Hj @("kanban","show",$Arg,"--json")
      $last = @($s.comments | Select-Object -Last 1 | ForEach-Object { $_.body })[0]
      $sum = [string]$s.latest_summary
      $ids = @(CardAttempts $s)
      $work = @($ids | Where-Object { $p = Join-Path $ATT "$_.json"; (Test-Path $p) -and -not (Get-Content $p -Raw | ConvertFrom-Json).brief.verify_of })
      $v = VerifyFor $work
      $settled = $null
      if ($v -and ([string]$v.verdict -in @("pass","fail"))) {
        try { $settled = SettleCard $s.task.id $v } catch { $settled = @{ ok = $false; error = (Scrub $_.Exception.Message) } }
        try { $s = Hj @("kanban","show",$Arg,"--json") } catch { }
      }
      $compact = ResultSummary $s.task.id $s.task.status $v $work $(if ($v) { $v.attempt } else { $null })
      if ($settled) { $compact.settled = $settled }
      $fullObj = @{ ok = $true; card = $s.task.id; status = $s.task.status; attempts = @($ids | ForEach-Object { AttemptInfo $_ }); verify = $v; summary = $sum; last_comment = $last; branch = $s.task.branch_name; settled = $settled }
      Emit-Result $compact $fullObj
    }
    "settle" {
      if (-not $Arg) { throw "card id required" }
      $s = Hj @("kanban","show",$Arg,"--json")
      $ids = @(CardAttempts $s)
      $work = @($ids | Where-Object { $p = Join-Path $ATT "$_.json"; (Test-Path $p) -and -not (Get-Content $p -Raw | ConvertFrom-Json).brief.verify_of })
      $v = VerifyFor $work
      $settled = SettleCard $s.task.id $v
      Out-Json @{ ok = [bool]$settled.ok; card = $s.task.id; status = $settled.status; verdict = $v.verdict; settled = $settled }
    }
    default { Out-Json @{ ok = $false; error = "verbs: status [card] | handoff <brief.json> [-DryRun] | result <card> [-Full] [-OutFile path] | settle <card>" }; exit 2 }
  }
} catch { Out-Json @{ ok = $false; error = (Scrub $_.Exception.Message) }; exit 1 }
