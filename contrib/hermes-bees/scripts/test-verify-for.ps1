# Unit check: VerifyFor accepts worker_claims shape A (verdict/commands/secret_scan)
# and shape B (checks[]/passed). Also leased-hash compare vs telemetry extras vs scope_violation.
# Never prints secrets. Exit 0 on pass.
$ErrorActionPreference = "Stop"
$bees = Join-Path $PSScriptRoot "bees.ps1"
$src = Get-Content $bees -Raw
$cut = $src.IndexOf("`r`ntry {"); if ($cut -lt 0) { $cut = $src.IndexOf("`ntry {") }
if ($cut -lt 0) { throw "could not find try block in bees.ps1" }
$tmpFn = Join-Path ([IO.Path]::GetTempPath()) ("bees-fns-" + [guid]::NewGuid().ToString("n") + ".ps1")
$tmpAtt = Join-Path ([IO.Path]::GetTempPath()) ("bees-att-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $tmpAtt | Out-Null
$env:BEES_ATT_DIR = $tmpAtt
try {
  [IO.File]::WriteAllText($tmpFn, $src.Substring(0, $cut))
  . $tmpFn
  function New-Pair($name, $claims, $vfiles = $null, $wfiles = $null, $assigned = @("calc.py", "test_calc.py"), [switch]$OmitWorkAssigned, [switch]$EmptyAssigned, $vAssigned = $null) {
    $work = "att_" + ([guid]::NewGuid().ToString("n").Substring(0,16))
    $ver = "att_" + ([guid]::NewGuid().ToString("n").Substring(0,16))
    $files = @(@{ path = "calc.py"; sha256 = "abc" }, @{ path = "test_calc.py"; sha256 = "def" })
    if ($null -eq $wfiles) { $wfiles = $files }
    if ($null -eq $vfiles) { $vfiles = $wfiles }
    $wbrief = @{ project = "calc" }
    if ($EmptyAssigned) { $wbrief.assigned_files = @() }
    elseif (-not $OmitWorkAssigned) { $wbrief.assigned_files = @($assigned) }
    $verifyAssigned = if ($null -ne $vAssigned) { @($vAssigned) } else { if ($OmitWorkAssigned -or $EmptyAssigned) { @() } else { @($assigned) } }
    $wres = @{ patch = @{ files = @($wfiles); diff = "diff --git a/calc.py b/calc.py`n" } }
    $vres = @{ patch = @{ files = @($vfiles); diff = "diff --git a/calc.py b/calc.py`n" }; worker_claims = $claims }
    @{ attempt_id = $work; state = "succeeded"; brief = $wbrief } | ConvertTo-Json -Depth 6 -Compress | Set-Content (Join-Path $tmpAtt "$work.json")
    $wres | ConvertTo-Json -Depth 6 -Compress | Set-Content (Join-Path $tmpAtt "$work.result.json")
    @{ attempt_id = $ver; state = "succeeded"; brief = @{ verify_of = $work; project = "calc"; assigned_files = @($verifyAssigned) } } | ConvertTo-Json -Depth 6 -Compress | Set-Content (Join-Path $tmpAtt "$ver.json")
    $vres | ConvertTo-Json -Depth 6 -Compress | Set-Content (Join-Path $tmpAtt "$ver.result.json")
    return $work
  }
  $fail = $false
  function AsBool($v) {
    if ($v -is [bool]) { return $v }
    if ($null -eq $v) { return $false }
    if ($v -is [System.Array] -or $v -is [System.Collections.IEnumerable]) { return (@($v).Count -gt 0) }
    return [bool]$v
  }
  function Check($name, $work, $expect, $expectMatch = $null, $expectScope = $null, $expectTel = $null, $expectScopeHas = $null, $expectLeaseMissing = $null) {
    $o = VerifyFor @($work)
    $pass = ($o.verdict -eq $expect)
    $why = @()
    if (-not $pass) { $why += "verdict" }
    if ($null -ne $expectMatch -and [bool]$o.patch_matches_work -ne [bool]$expectMatch) { $pass = $false; $why += "patch_matches" }
    if ($null -ne $expectScope -and (AsBool $o.scope_violation) -ne [bool]$expectScope) { $pass = $false; $why += "scope_violation" }
    if ($null -ne $expectTel) {
      $tel = @($o.telemetry_extras)
      $okTel = $false
      foreach ($p in $tel) { if ([string]$p -like $expectTel -or [string]$p -eq $expectTel) { $okTel = $true } }
      if (-not $okTel) { $pass = $false; $why += "telemetry_extras" }
    }
    if ($null -ne $expectScopeHas -and -not (@($o.scope_extras) -contains [string]$expectScopeHas)) { $pass = $false; $why += "scope_extras" }
    if ($null -ne $expectLeaseMissing -and (AsBool $o.lease_missing) -ne [bool]$expectLeaseMissing) { $pass = $false; $why += "lease_missing" }
    if (-not $pass) { $script:fail = $true }
    $scopeList = @($o.scope_extras) -join ","
    $telList = @($o.telemetry_extras) -join ","
    $misList = @($o.mismatch) -join ","
    Write-Output ("case={0} verdict={1} expect={2} claimed={3} failed_cmds={4} secret_hits={5} patch_matches={6} scope_violation={7} extras={8} telemetry={9} mismatch={10} pass={11} {12}" -f $name, $o.verdict, $expect, $o.claimed, $o.failed_cmds, $o.secret_hits, $o.patch_matches_work, $o.scope_violation, $scopeList, $telList, $misList, $pass, ($(if ($why) { "why=" + ($why -join ",") } else { "" })))
  }
  $assigned = @("calc.py", "test_calc.py")
  $passClaims = @{ verdict = "pass"; commands = @(@{ cmd = "python3 -m unittest -q test_calc.py"; rc = 0; tail = "" }); secret_scan = @{ tool = "regex"; hits = @() }; not_run = @() }
  $w = New-Pair "A-pass" $passClaims $null $null $assigned
  Check "A-pass" $w "pass"
  $w = New-Pair "A-fail-rc" @{ verdict = "pass"; commands = @(@{ cmd = "python3 -m unittest -q test_calc.py"; rc = 1; tail = "fail" }); secret_scan = @{ tool = "regex"; hits = @() } } $null $null $assigned
  Check "A-fail-rc" $w "fail"
  $w = New-Pair "A-fail-hits" @{ verdict = "pass"; commands = @(@{ cmd = "x"; rc = 0; tail = "" }); secret_scan = @{ tool = "regex"; hits = @(@{ file = "a"; rule = "token" }) } } $null $null $assigned
  Check "A-fail-hits" $w "fail"
  $w = New-Pair "B-pass" @{ checks = @(
      @{ name = "apply"; command = "git apply"; passed = $true },
      @{ name = "unit"; command = "python3 -m unittest -q test_calc.py"; passed = $true },
      @{ name = "secret_scan"; command = "regex"; passed = $true }
    ) } $null $null $assigned
  Check "B-pass" $w "pass"
  $w = New-Pair "B-fail-check" @{ checks = @(
      @{ name = "unit"; command = "python3 -m unittest -q test_calc.py"; passed = $false },
      @{ name = "secret_scan"; command = "regex"; passed = $true }
    ) } $null $null $assigned
  Check "B-fail-check" $w "fail"
  $w = New-Pair "B-no-secret" @{ checks = @(@{ name = "unit"; command = "python3 -m unittest"; passed = $true }) } $null $null $assigned
  Check "B-no-secret" $w "fail"

  $leased = @(@{ path = "calc.py"; sha256 = "abc" }, @{ path = "test_calc.py"; sha256 = "def" })
  $withTel = $leased + @(@{ path = "shots/verify-pilot/PROGRESS.log"; sha256 = "tel" })
  $w = New-Pair "tel-progress" $passClaims $withTel $leased $assigned
  Check "tel-progress" $w "pass" $true $false "*PROGRESS.log"

  $mismatchFiles = @(@{ path = "calc.py"; sha256 = "XXX" }, @{ path = "test_calc.py"; sha256 = "def" })
  $w = New-Pair "hash-mismatch" $passClaims $mismatchFiles $leased $assigned
  Check "hash-mismatch" $w "fail" $false $false

  $extraSrc = $leased + @(@{ path = "extra.py"; sha256 = "eee" })
  $w = New-Pair "scope-extra" $passClaims $extraSrc $leased $assigned
  Check "scope-extra" $w "fail" $true $true

  # S4: the lease comes only from the work attempt record brief.assigned_files.
  $w = New-Pair "lease-missing-fails" $passClaims -OmitWorkAssigned
  Check "lease-missing-fails" $w "fail" -expectLeaseMissing $true

  $w = New-Pair "lease-missing-empty-list" $passClaims -EmptyAssigned
  Check "lease-missing-empty-list" $w "fail" -expectLeaseMissing $true

  $w = New-Pair "work-attempt-record-missing" $passClaims $null $null $assigned
  Remove-Item (Join-Path $tmpAtt "$w.json") -Force
  Check "work-attempt-record-missing" $w "fail" -expectLeaseMissing $true

  $calcAndExtra = @(@{ path = "calc.py"; sha256 = "abc" }, @{ path = "extra.py"; sha256 = "eee"; in_assigned_scope = $true })
  $calcAndExtraVerify = @(@{ path = "calc.py"; sha256 = "abc" }, @{ path = "extra.py"; sha256 = "eee" })
  $w = New-Pair "in-assigned-scope-no-widen" $passClaims $calcAndExtraVerify $calcAndExtra @("calc.py")
  Check "in-assigned-scope-no-widen" $w "fail" $true $true -expectScopeHas "extra.py"

  $verifyWiden = @(@{ path = "calc.py"; sha256 = "abc" }, @{ path = "test_calc.py"; sha256 = "def" }, @{ path = "extra.py"; sha256 = "eee" })
  $w = New-Pair "verify-brief-cannot-widen" $passClaims $verifyWiden $verifyWiden $assigned -vAssigned @("calc.py", "test_calc.py", "extra.py")
  Check "verify-brief-cannot-widen" $w "fail" $true $true -expectScopeHas "extra.py"

  $pkgFiles = @(@{ path = "pkg/a.py"; sha256 = "pkg" })
  $w = New-Pair "dir-prefix-lease" $passClaims $pkgFiles $pkgFiles @("pkg/")
  Check "dir-prefix-lease" $w "pass" $true $false

  if ($fail) { Write-Output "verify_for_check=FAIL"; exit 2 }
  Write-Output "verify_for_check=ok"

  $lf = $false
  function LCheck($name, $cond) {
    if (-not $cond) { $script:lf = $true }
    Write-Output ("lifecycle={0} pass={1}" -f $name, [bool]$cond)
  }
  $p1 = SettlePlan "blocked" "needs_input" "pass"
  LCheck "settle-pass-blocked" (($p1.action -eq "review") -and [bool]$p1.unblock)
  $p1 = SettlePlan "review" "" "pass"
  LCheck "settle-pass-review" ($p1.action -eq "noop")
  $p1 = SettlePlan "done" "" "pass"
  LCheck "settle-pass-done" ($p1.action -eq "noop")
  $p1 = SettlePlan "ready" "" "fail"
  LCheck "settle-fail-ready" ($p1.action -eq "block")
  $p1 = SettlePlan "blocked" "needs_input" "fail"
  LCheck "settle-fail-blocked" ($p1.action -eq "noop")
  $p1 = SettlePlan "running" "" "none"
  LCheck "settle-pending" ($p1.action -eq "noop")
  $p1 = SettlePlan "running" "" "pass"
  LCheck "settle-pass-running" (($p1.action -eq "review") -and -not [bool]$p1.unblock)
  $fakeV = @{ verdict = "pass"; claimed = "pass"; patch_matches_work = $true; scope_violation = $false; secret_hits = 0; failed_cmds = 0; telemetry_extras = @("shots/x/PROGRESS.log"); attempt = "att_aa" }
  $sum = ResultSummary "t_x" "blocked" $fakeV @() "att_aa"
  LCheck "summary-fields" (($sum.verdict -eq "pass") -and ($sum.claimed -eq "pass") -and ($sum.patch_matches_work -eq $true) -and ($sum.scope_violation -eq $false) -and ($sum.secret_hits -eq 0) -and ($sum.failed_cmds -eq 0) -and ($sum.telemetry_extras[0] -like "*PROGRESS.log") -and ($sum.card -eq "t_x"))
  $j = $sum | ConvertTo-Json -Compress -Depth 6
  LCheck "compact-not-truncated" (($j -notmatch "truncated") -and ($j.Length -gt 0) -and ($j -match "telemetry_extras"))
  if ($lf) { Write-Output "lifecycle_check=FAIL"; exit 2 }
  Write-Output "lifecycle_check=ok"

  $cf = $false
  function CCheck($name, $cond) {
    if (-not $cond) { $script:cf = $true }
    Write-Output ("cli_contract={0} pass={1}" -f $name, [bool]$cond)
  }
  $plain = ParseHermesOut "Unblocked t_abc: verify pass; resume to record verdict`n" 0
  CCheck "unblock-plain-ok" ($plain.ok -and ($plain.exit_code -eq 0) -and ($null -eq $plain.json) -and -not $plain.unrecognized_json)
  $js = ParseHermesOut "{`"task`":{`"id`":`"t_abc`",`"status`":`"review`"}}" 0
  CCheck "show-json-ok" ($js.ok -and $js.json.task.status -eq "review")
  $bad = ParseHermesOut "hermes: error: unrecognized arguments: --json`n" 2
  CCheck "unrecognized-json-flag" ((-not $bad.ok) -and $bad.unrecognized_json -and ($bad.exit_code -eq 2))
  $failtxt = ParseHermesOut "error: task is not blocked" 1
  CCheck "nonzero-exit-no-json" ((-not $failtxt.ok) -and ($failtxt.exit_code -eq 1) -and ($null -eq $failtxt.json))
  $mixed = ParseHermesOut "note: ok`n{`"ok`":true,`"id`":`"t_1`"}`n" 0
  CCheck "json-after-preamble" ($mixed.ok -and $mixed.json.ok -eq $true -and $mixed.json.id -eq "t_1")
  CCheck "find-verb-plain" ((FindKanbanVerb @("kanban","unblock","t_x")) -eq "unblock")
  CCheck "find-verb-profile" ((FindKanbanVerb @("-p","beekeeper","kanban","dispatch","--max","1")) -eq "dispatch")

  $ownedTmp = Join-Path ([IO.Path]::GetTempPath()) ("bees-owned-" + [guid]::NewGuid().ToString("n") + ".json")
  $env:BEES_OWNED_FILE = $ownedTmp
  try {
    RegisterOwned "pilot-calc-0116"
    RegisterOwned "pilot-calc-0116"
    RegisterOwned "other-card"
    $o = Get-Content $ownedTmp -Raw | ConvertFrom-Json
    $ids = @($o.task_ids)
    CCheck "owned-registry-idempotent" (($ids -contains "pilot-calc-0116") -and ($ids -contains "other-card") -and ($ids.Count -eq 2))
  } finally {
    Remove-Item $ownedTmp -Force -ErrorAction SilentlyContinue
    Remove-Item Env:BEES_OWNED_FILE -ErrorAction SilentlyContinue
  }

  if ($cf) { Write-Output "cli_contract_check=FAIL"; exit 2 }
  Write-Output "cli_contract_check=ok"
} finally {
  Remove-Item $tmpFn -Force -ErrorAction SilentlyContinue
  Remove-Item $tmpAtt -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item Env:BEES_ATT_DIR -ErrorAction SilentlyContinue
}
