#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$JobManifest,

    [Parameter(Mandatory = $true)]
    [string]$Checkout,

    [Parameter(Mandatory = $true)]
    [string]$ResultManifest,

    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# BEGIN BEE-RUN CONTRACT
$script:BeeRunContractJson = @'
{
  "schema_version": 1,
  "plan_kind": "bee-run/command-plan",
  "result_kind": "bee-run/result-manifest",
  "failure_policy": "fail-fast",
  "required_job_fields": ["job_id", "steps"],
  "required_step_fields": ["id", "command"],
  "result_step_fields": ["index", "id", "name", "command", "status", "exit_code", "duration_ms", "timed_out", "stdout", "stderr", "output_truncated"],
  "default_timeout_seconds": 900,
  "max_timeout_seconds": 86400,
  "max_steps": 1000,
  "max_output_chars": 20000,
  "redaction_marker": "[REDACTED]",
  "sensitive_output_patterns": [
    {"regex": "(?i)(authorization:\\s*(?:bearer|basic)\\s+)\\S+", "replacement": "$1[REDACTED]"},
    {"regex": "(?i)((?:password|passwd|token|secret|api[_-]?key|credential)\\s*[=:]\\s*)[^\\s]+", "replacement": "$1[REDACTED]"},
    {"regex": "(?i)(https?://[^/\\s:@]+:)[^/\\s@]+@", "replacement": "$1[REDACTED]@"}
  ]
}
'@
# END BEE-RUN CONTRACT

$script:BeeRunContract = $script:BeeRunContractJson | ConvertFrom-Json
$script:IsWindowsHost = ($env:OS -eq 'Windows_NT')

function Get-OptionalProperty {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Default = $null
    )
    if ($null -eq $Object) {
        return ,$Default
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return ,$Default
    }
    return ,$property.Value
}

function Test-SafeId {
    param([object]$Value)
    if ($null -eq $Value) {
        return $false
    }
    return ([string]$Value) -match '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
}

function Test-PathWithin {
    param(
        [string]$Child,
        [string]$Root
    )
    $separator = [IO.Path]::DirectorySeparatorChar
    $alternate = [IO.Path]::AltDirectorySeparatorChar
    $childFull = [IO.Path]::GetFullPath($Child).TrimEnd($separator, $alternate)
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd($separator, $alternate)
    if (-not $script:IsWindowsHost) {
        if ($childFull -ceq $rootFull) {
            return $true
        }
        $prefix = $rootFull + $separator
        return $childFull.StartsWith($prefix, [StringComparison]::Ordinal)
    }
    if ([string]::Equals($childFull, $rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $prefix = $rootFull + $separator
    return $childFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Get-RealPath {
    param(
        [string]$Path,
        [int]$Depth = 0
    )
    if ($Depth -gt 40) {
        throw 'too many symbolic links while resolving a path'
    }
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    $relative = $full.Substring($root.Length)
    $current = $root
    foreach ($part in ($relative -split '[\\/]')) {
        if ([string]::IsNullOrEmpty($part)) {
            continue
        }
        $candidate = Join-Path $current $part
        $item = Get-Item -LiteralPath $candidate -Force
        $linkTypeProperty = $item.PSObject.Properties['LinkType']
        $linkType = $null
        if ($null -ne $linkTypeProperty) {
            $linkType = $linkTypeProperty.Value
        }
        if (-not [string]::IsNullOrEmpty([string]$linkType)) {
            $targetProperty = $item.PSObject.Properties['Target']
            $target = $null
            if ($null -ne $targetProperty) {
                $target = $targetProperty.Value
            }
            if ($target -is [System.Array]) {
                $target = $target[0]
            }
            if ([string]::IsNullOrWhiteSpace([string]$target)) {
                throw 'cannot resolve a symbolic link safely'
            }
            if ([IO.Path]::IsPathRooted([string]$target)) {
                $candidate = [IO.Path]::GetFullPath([string]$target)
            }
            else {
                $candidate = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $candidate) ([string]$target)))
            }
            $current = Get-RealPath -Path $candidate -Depth ($Depth + 1)
        }
        else {
            $current = $candidate
        }
    }
    return $current
}

function Resolve-Checkout {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'checkout path must not be empty'
    }
    $full = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Container)) {
        throw 'checkout directory does not exist'
    }
    return (Get-RealPath -Path $full)
}

function Read-JobManifest {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'job manifest path must not be empty'
    }
    $full = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw 'job manifest does not exist'
    }
    $item = Get-Item -LiteralPath $full
    if ($item.Length -gt 1048576) {
        throw 'job manifest exceeds the 1 MiB limit'
    }
    $text = [IO.File]::ReadAllText($full, [Text.Encoding]::UTF8)
    try {
        $job = $text | ConvertFrom-Json
    }
    catch {
        throw 'job manifest is not valid JSON'
    }
    if ($null -eq $job -or $job -is [System.Array]) {
        throw 'job manifest must be a JSON object'
    }
    return $job
}

function Resolve-TimeoutSeconds {
    param(
        [object]$Value,
        [string]$Context
    )
    if ($null -eq $Value) {
        return [int]$script:BeeRunContract.default_timeout_seconds
    }
    if ($Value -is [bool]) {
        throw "$Context must be an integer number of seconds"
    }
    $parsed = 0
    if (-not [int]::TryParse([string]$Value, [ref]$parsed)) {
        throw "$Context must be an integer number of seconds"
    }
    if ($parsed -lt 1 -or $parsed -gt [int]$script:BeeRunContract.max_timeout_seconds) {
        throw "$Context is outside the permitted timeout range"
    }
    return $parsed
}

function ConvertTo-OptionalBool {
    param(
        [object]$Value,
        [string]$Context
    )
    if ($null -eq $Value) {
        return $false
    }
    if ($Value -is [bool]) {
        return [bool]$Value
    }
    throw "$Context must be true or false"
}

function ConvertTo-CommandText {
    param(
        [object]$Value,
        [string]$Context
    )
    if ($Value -is [string]) {
        if ([string]::IsNullOrWhiteSpace([string]$Value)) {
            throw "$Context command must not be empty"
        }
        return [string]$Value
    }
    if ($Value -is [System.Array]) {
        if ($Value.Count -eq 0) {
            throw "$Context command must not be empty"
        }
        $quoted = foreach ($argument in $Value) {
            if (-not ($argument -is [string]) -or [string]::IsNullOrEmpty([string]$argument)) {
                throw "$Context command arguments must be non-empty strings"
            }
            "'" + ([string]$argument).Replace("'", "''") + "'"
        }
        return '& ' + ($quoted -join ' ')
    }
    throw "$Context command must be a non-empty string or array of strings"
}

function New-CommandPlan {
    param(
        [object]$Job,
        [string]$CheckoutRoot
    )
    foreach ($field in $script:BeeRunContract.required_job_fields) {
        if ($null -eq (Get-OptionalProperty -Object $Job -Name $field -Default $null)) {
            throw "job manifest is missing $field"
        }
    }
    $jobId = [string](Get-OptionalProperty -Object $Job -Name 'job_id' -Default '')
    if (-not (Test-SafeId -Value $jobId)) {
        throw 'job_id is not a safe identifier'
    }
    $stepsValue = Get-OptionalProperty -Object $Job -Name 'steps' -Default $null
    if ($null -eq $stepsValue -or -not ($stepsValue -is [System.Array])) {
        throw 'job manifest steps must be a non-empty array'
    }
    $steps = @($stepsValue)
    if ($steps.Count -lt 1) {
        throw 'job manifest must contain at least one step'
    }
    if ($steps.Count -gt [int]$script:BeeRunContract.max_steps) {
        throw 'job manifest contains too many steps'
    }
    $defaultTimeout = Resolve-TimeoutSeconds -Value (Get-OptionalProperty -Object $Job -Name 'timeout_seconds' -Default $null) -Context 'job timeout_seconds'
    $seen = New-Object System.Collections.Hashtable ([StringComparer]::Ordinal)
    $planned = New-Object System.Collections.ArrayList
    $index = 0
    foreach ($step in $steps) {
        $index += 1
        foreach ($field in $script:BeeRunContract.required_step_fields) {
            if ($null -eq (Get-OptionalProperty -Object $step -Name $field -Default $null)) {
                throw "step $index is missing $field"
            }
        }
        $stepId = [string](Get-OptionalProperty -Object $step -Name 'id' -Default '')
        if (-not (Test-SafeId -Value $stepId)) {
            throw "step $index has an unsafe id"
        }
        if ($seen.ContainsKey($stepId)) {
            throw "duplicate step id: $stepId"
        }
        $seen[$stepId] = $true
        $command = ConvertTo-CommandText -Value (Get-OptionalProperty -Object $step -Name 'command' -Default $null) -Context "step $stepId"
        $timeout = Resolve-TimeoutSeconds -Value (Get-OptionalProperty -Object $step -Name 'timeout_seconds' -Default $null) -Context "step $stepId timeout_seconds"
        if ($timeout -eq [int]$script:BeeRunContract.default_timeout_seconds -and $null -eq (Get-OptionalProperty -Object $step -Name 'timeout_seconds' -Default $null)) {
            $timeout = $defaultTimeout
        }
        $cwdValue = [string](Get-OptionalProperty -Object $step -Name 'cwd' -Default '.')
        if ([string]::IsNullOrWhiteSpace($cwdValue)) {
            $cwdValue = '.'
        }
        if ([IO.Path]::IsPathRooted($cwdValue)) {
            $candidate = $cwdValue
        }
        else {
            $candidate = Join-Path $CheckoutRoot $cwdValue
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            throw "step $stepId cwd does not exist"
        }
        $cwd = Get-RealPath -Path $candidate
        if (-not (Test-PathWithin -Child $cwd -Root $CheckoutRoot)) {
            throw "step $stepId cwd escapes the checkout"
        }
        $continueOnError = ConvertTo-OptionalBool -Value (Get-OptionalProperty -Object $step -Name 'continue_on_error' -Default $null) -Context "step $stepId continue_on_error"
        $name = [string](Get-OptionalProperty -Object $step -Name 'name' -Default $stepId)
        if ([string]::IsNullOrWhiteSpace($name)) {
            $name = $stepId
        }
        [void]$planned.Add([pscustomobject]@{
            index = $index
            id = $stepId
            name = $name
            command = $command
            cwd = $cwd
            timeout_seconds = [int]$timeout
            continue_on_error = $continueOnError
        })
    }
    return [pscustomobject]@{
        schema_version = [int]$script:BeeRunContract.schema_version
        kind = [string]$script:BeeRunContract.plan_kind
        job_id = $jobId
        checkout = $CheckoutRoot
        failure_policy = [string]$script:BeeRunContract.failure_policy
        steps = @($planned)
    }
}

function New-RedactionContext {
    param([object]$Job)
    $literals = New-Object System.Collections.ArrayList
    $redactValue = Get-OptionalProperty -Object $Job -Name 'redact' -Default $null
    if ($null -ne $redactValue) {
        foreach ($entry in @($redactValue)) {
            if (-not ($entry -is [string]) -or [string]::IsNullOrEmpty([string]$entry)) {
                throw 'redact entries must be non-empty strings'
            }
            [void]$literals.Add([string]$entry)
        }
    }
    $sensitiveName = '(?i)(token|secret|password|passwd|api[_-]?key|credential|authorization)'
    $environmentValues = [Environment]::GetEnvironmentVariables()
    foreach ($entry in $environmentValues.GetEnumerator()) {
        if ($literals.Count -ge 256) {
            break
        }
        if ([string]$entry.Key -match $sensitiveName -and $entry.Value -is [string]) {
            $value = [string]$entry.Value
            if ($value.Length -ge 8 -and $value -ne [string]$script:BeeRunContract.redaction_marker) {
                [void]$literals.Add($value)
            }
        }
    }
    return [pscustomobject]@{
        literals = @($literals)
        marker = [string]$script:BeeRunContract.redaction_marker
        rules = @($script:BeeRunContract.sensitive_output_patterns)
    }
}

function Redact-Text {
    param(
        [object]$Text,
        [object]$Context
    )
    if ($null -eq $Text) {
        return ''
    }
    $result = [string]$Text
    foreach ($literal in @($Context.literals)) {
        if (-not [string]::IsNullOrEmpty([string]$literal)) {
            $result = $result.Replace([string]$literal, [string]$Context.marker)
        }
    }
    foreach ($rule in @($Context.rules)) {
        $result = [regex]::Replace($result, [string]$rule.regex, [string]$rule.replacement)
    }
    return $result
}

function Limit-Output {
    param([object]$Text)
    $value = [string]$Text
    $max = [int]$script:BeeRunContract.max_output_chars
    if ($value.Length -le $max) {
        return [pscustomobject]@{ text = $value; truncated = $false }
    }
    $head = [int][math]::Floor($max / 2)
    $tail = $max - $head
    $joined = $value.Substring(0, $head) + "`n... [output truncated] ...`n" + $value.Substring($value.Length - $tail)
    return [pscustomobject]@{ text = $joined; truncated = $true }
}

function Write-JsonFileAtomic {
    param(
        [string]$Path,
        [object]$Value
    )
    $full = [IO.Path]::GetFullPath($Path)
    $directory = Split-Path -Parent $full
    if ([string]::IsNullOrWhiteSpace($directory)) {
        $directory = (Get-Location).Path
    }
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
    $temporary = Join-Path $directory ('.bee-run-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $json = $Value | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $full -Force
}

function Get-PowerShellExecutable {
    $processPath = (Get-Process -Id $PID).Path
    if (-not [string]::IsNullOrWhiteSpace($processPath)) {
        return $processPath
    }
    if ($PSVersionTable.PSEdition -eq 'Core') {
        if ($script:IsWindowsHost) {
            return (Join-Path $PSHOME 'pwsh.exe')
        }
        return (Join-Path $PSHOME 'pwsh')
    }
    return (Join-Path $PSHOME 'powershell.exe')
}

function Read-TextFileSafe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return ''
    }
    try {
        return [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    }
    catch {
        return ''
    }
}

function Invoke-PlanStep {
    param(
        [object]$Step,
        [string]$PowerShellExecutable
    )
    $temporaryRoot = [IO.Path]::GetTempPath()
    $token = [guid]::NewGuid().ToString('N')
    $scriptFile = Join-Path $temporaryRoot ('bee-run-' + $token + '.ps1')
    $stdoutFile = Join-Path $temporaryRoot ('bee-run-' + $token + '.out')
    $stderrFile = Join-Path $temporaryRoot ('bee-run-' + $token + '.err')
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $timedOut = $false
    $exitCode = $null
    try {
        [IO.File]::WriteAllText($scriptFile, [string]$Step.command, (New-Object Text.UTF8Encoding($false)))
        $quotedScript = '"' + $scriptFile.Replace('"', '""') + '"'
        $arguments = @(
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            $quotedScript
        )
        $process = Start-Process -FilePath $PowerShellExecutable -ArgumentList $arguments -WorkingDirectory ([string]$Step.cwd) -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -PassThru -NoNewWindow
        $timeoutMilliseconds = [int]([int64]$Step.timeout_seconds * 1000)
        $finished = $process.WaitForExit($timeoutMilliseconds)
        if (-not $finished) {
            $timedOut = $true
            if ($script:IsWindowsHost) {
                try {
                    & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
                }
                catch {
                }
            }
            try {
                $process.Kill($true)
            }
            catch {
                try {
                    $process.Kill()
                }
                catch {
                }
            }
            try {
                [void]$process.WaitForExit(10000)
            }
            catch {
            }
            $exitCode = $null
        }
        else {
            try {
                $exitCode = [int]$process.ExitCode
            }
            catch {
                $exitCode = $null
            }
        }
    }
    finally {
        $timer.Stop()
        $stdout = Read-TextFileSafe -Path $stdoutFile
        $stderr = Read-TextFileSafe -Path $stderrFile
        foreach ($path in @($scriptFile, $stdoutFile, $stderrFile)) {
            try {
                Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
            }
            catch {
            }
        }
    }
    return [pscustomobject]@{
        exit_code = $exitCode
        duration_ms = [int][math]::Round($timer.Elapsed.TotalMilliseconds)
        timed_out = $timedOut
        stdout = $stdout
        stderr = $stderr
    }
}

$resultPath = [IO.Path]::GetFullPath($ResultManifest)
$startedAt = [DateTimeOffset]::UtcNow
$checkoutRoot = $null
$job = $null
$plan = $null
$redaction = $null

try {
    $redaction = New-RedactionContext -Job $null
    $checkoutRoot = Resolve-Checkout -Path $Checkout
    $job = Read-JobManifest -Path $JobManifest
    $redaction = New-RedactionContext -Job $job
    $plan = New-CommandPlan -Job $job -CheckoutRoot $checkoutRoot

    if ($PlanOnly) {
        $safeSteps = foreach ($step in @($plan.steps)) {
            [pscustomobject]@{
                index = $step.index
                id = $step.id
                name = $step.name
                command = Redact-Text -Text $step.command -Context $redaction
                cwd = $step.cwd
                timeout_seconds = $step.timeout_seconds
                continue_on_error = $step.continue_on_error
            }
        }
        $safePlan = [pscustomobject]@{
            schema_version = $plan.schema_version
            kind = $plan.kind
            job_id = $plan.job_id
            checkout = $plan.checkout
            failure_policy = $plan.failure_policy
            steps = @($safeSteps)
        }
        Write-JsonFileAtomic -Path $resultPath -Value $safePlan
        exit 0
    }

    $powerShellExecutable = Get-PowerShellExecutable
    $records = New-Object System.Collections.ArrayList
    $failure = $null
    foreach ($step in @($plan.steps)) {
        $outcome = Invoke-PlanStep -Step $step -PowerShellExecutable $powerShellExecutable
        if ($outcome.timed_out) {
            $status = 'timed_out'
        }
        elseif ($outcome.exit_code -eq 0) {
            $status = 'passed'
        }
        else {
            $status = 'failed'
        }
        $stdout = Limit-Output -Text (Redact-Text -Text $outcome.stdout -Context $redaction)
        $stderr = Limit-Output -Text (Redact-Text -Text $outcome.stderr -Context $redaction)
        $record = [pscustomobject]@{
            index = $step.index
            id = $step.id
            name = $step.name
            command = Redact-Text -Text $step.command -Context $redaction
            status = $status
            exit_code = $outcome.exit_code
            duration_ms = $outcome.duration_ms
            timed_out = [bool]$outcome.timed_out
            stdout = $stdout.text
            stderr = $stderr.text
            output_truncated = [bool]($stdout.truncated -or $stderr.truncated)
        }
        [void]$records.Add($record)
        if ($null -eq $failure -and $status -ne 'passed') {
            $reason = if ($outcome.timed_out) { 'timeout' } else { 'non_zero_exit' }
            $failure = [pscustomobject]@{
                step_id = $step.id
                exit_code = $outcome.exit_code
                reason = $reason
            }
        }
        if ($null -ne $failure -and -not [bool]$step.continue_on_error) {
            break
        }
    }

    $finishedAt = [DateTimeOffset]::UtcNow
    $manifest = [pscustomobject]@{
        schema_version = [int]$script:BeeRunContract.schema_version
        kind = [string]$script:BeeRunContract.result_kind
        job_id = $plan.job_id
        checkout = $plan.checkout
        status = $(if ($null -eq $failure) { 'passed' } else { 'failed' })
        failure_policy = [string]$script:BeeRunContract.failure_policy
        started_at = $startedAt.ToString('o')
        finished_at = $finishedAt.ToString('o')
        duration_ms = [int][math]::Round(($finishedAt - $startedAt).TotalMilliseconds)
        steps = @($records)
        failure = $failure
    }
    Write-JsonFileAtomic -Path $resultPath -Value $manifest
    if ($null -eq $failure) {
        exit 0
    }
    exit 1
}
catch {
    $message = 'runner failed before a result could be produced'
    try {
        if ($null -eq $redaction) {
            $redaction = New-RedactionContext -Job $null
        }
        $message = Redact-Text -Text ([string]$_.Exception.Message) -Context $redaction
    }
    catch {
    }
    $reason = if ($null -eq $plan) { 'invalid_job_manifest' } else { 'runner_error' }
    $finishedAt = [DateTimeOffset]::UtcNow
    $manifest = [pscustomobject]@{
        schema_version = [int]$script:BeeRunContract.schema_version
        kind = [string]$script:BeeRunContract.result_kind
        job_id = $(if ($null -ne $plan) { $plan.job_id } else { $null })
        checkout = $checkoutRoot
        status = 'failed'
        failure_policy = [string]$script:BeeRunContract.failure_policy
        started_at = $startedAt.ToString('o')
        finished_at = $finishedAt.ToString('o')
        duration_ms = [int][math]::Round(($finishedAt - $startedAt).TotalMilliseconds)
        steps = @()
        failure = [pscustomobject]@{
            step_id = $null
            exit_code = $null
            reason = $reason
            message = $message
        }
    }
    try {
        Write-JsonFileAtomic -Path $resultPath -Value $manifest
    }
    catch {
        [Console]::Error.WriteLine('bee-run: could not write the result manifest')
    }
    exit 1
}
