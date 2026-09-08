[CmdletBinding()]
param(
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 15,

    # Zero means keep trying until the matrix is complete or the process is stopped.
    [ValidateRange(0, 100000)]
    [int]$MaxAttempts = 0,

    [switch]$Once,
    [switch]$ResetSession,
    [switch]$CheckOnly,

    # Leave blank to use the model configured for the Codex CLI.
    [string]$Model = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot

# Allow Git commands launched by this runner to inspect this repository even
# when Codex's managed Windows process uses a different security identity.
# This is process-scoped and does not modify the user's global Git config.
$gitConfigCount = 0
$gitSafeRoot = $projectRoot.Replace("\", "/")
if ($env:GIT_CONFIG_COUNT -match '^\d+$') {
    $gitConfigCount = [int]$env:GIT_CONFIG_COUNT
}
$safeDirectoryPresent = $false
for ($gitIndex = 0; $gitIndex -lt $gitConfigCount; $gitIndex++) {
    $existingKey = [Environment]::GetEnvironmentVariable("GIT_CONFIG_KEY_$gitIndex", "Process")
    $existingValue = [Environment]::GetEnvironmentVariable("GIT_CONFIG_VALUE_$gitIndex", "Process")
    if ($existingKey -eq "safe.directory" -and $existingValue -eq $gitSafeRoot) {
        $safeDirectoryPresent = $true
        break
    }
}
if (-not $safeDirectoryPresent) {
    [Environment]::SetEnvironmentVariable("GIT_CONFIG_KEY_$gitConfigCount", "safe.directory", "Process")
    [Environment]::SetEnvironmentVariable("GIT_CONFIG_VALUE_$gitConfigCount", $gitSafeRoot, "Process")
    $env:GIT_CONFIG_COUNT = [string]($gitConfigCount + 1)
}

$artifactRoot = Join-Path $projectRoot ".uat-artifacts"
$automationRoot = Join-Path $artifactRoot "automation"
$statePath = Join-Path $automationRoot "uat-codex-loop-state.json"
$stopPath = Join-Path $automationRoot "STOP"
New-Item -ItemType Directory -Path $automationRoot -Force | Out-Null

function Write-RunnerLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$stamp] $Message"
}

function Get-LatestUatMatrix {
    $matrices = Get-ChildItem -LiteralPath $artifactRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^(setup|reset)-" } |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Filter "consolidated-44-scenario-matrix.md" -ErrorAction SilentlyContinue
        } |
        Sort-Object LastWriteTime -Descending

    return $matrices | Select-Object -First 1
}

function Get-UntestedCount {
    param([System.IO.FileInfo]$Matrix)
    if (-not $Matrix) { return $null }

    foreach ($line in Get-Content -LiteralPath $Matrix.FullName) {
        if ($line -match '^\|\s*Untested\s*\|\s*(\d+)\s*\|') {
            return [int]$Matches[1]
        }
    }
    return $null
}

function Read-RunnerState {
    if (-not (Test-Path -LiteralPath $statePath)) { return $null }
    try {
        return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    } catch {
        Write-Warning "The runner state was unreadable and will be replaced: $($_.Exception.Message)"
        return $null
    }
}

function Save-RunnerState {
    param(
        [AllowNull()][string]$SessionId,
        [int]$Attempt,
        [int]$ExitCode,
        [string]$LogPath
    )
    [ordered]@{
        session_id = $SessionId
        attempt = $Attempt
        last_exit_code = $ExitCode
        last_log = $LogPath
        updated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
}

function Find-SessionId {
    param([string]$LogPath)
    if (-not (Test-Path -LiteralPath $LogPath)) { return $null }

    foreach ($line in Get-Content -LiteralPath $LogPath) {
        if ($line -match '"thread_id"\s*:\s*"([0-9a-fA-F-]{36})"') {
            return $Matches[1]
        }
        if ($line -match '"session_id"\s*:\s*"([0-9a-fA-F-]{36})"') {
            return $Matches[1]
        }
    }
    return $null
}

function Test-CorruptCodexSession {
    param(
        [string]$LogPath,
        [AllowEmptyString()][string]$InvocationFailureText = ""
    )

    # These failures describe an unusable saved conversation state. Retrying the
    # same session cannot repair it because the missing tool result is historical.
    $corruptionPatterns = @(
        "Custom tool call output is missing",
        "tool call output.*missing",
        "failed to load.*(thread|session|rollout)",
        "(thread|session|rollout).*(not found|is missing)"
    )

    foreach ($pattern in $corruptionPatterns) {
        if ($InvocationFailureText -match $pattern) { return $true }
    }

    if (-not (Test-Path -LiteralPath $LogPath)) { return $false }

    # Only recognize a top-level Codex error record. Do not search the entire
    # JSONL log: command output may legitimately quote old errors or this script.
    foreach ($line in Get-Content -LiteralPath $LogPath -ErrorAction SilentlyContinue) {
        if ($line -match '^\d{4}-\d{2}-\d{2}T\S+\s+ERROR\s+codex_core::util:\s+Custom tool call output is missing') {
            return $true
        }

        if ($line.StartsWith('{')) {
            try {
                $event = $line | ConvertFrom-Json -ErrorAction Stop
                if ($event.type -in @("error", "turn.failed") -and $event.message) {
                    foreach ($pattern in $corruptionPatterns) {
                        if ([string]$event.message -match $pattern) { return $true }
                    }
                }
            } catch {
                # A malformed or partial JSONL line is not evidence of corruption.
            }
        }
    }
    return $false
}

function Test-CodexUsageLimit {
    param(
        [AllowEmptyString()][string]$InvocationFailureText = "",
        [string]$LogPath = ""
    )
    $usagePatterns = @(
        "usage limit",
        "rate limit",
        "too many requests",
        "quota exceeded",
        "status(code)?\s*429",
        "HTTP\s*429"
    )
    foreach ($pattern in $usagePatterns) {
        if ($InvocationFailureText -match $pattern) { return $true }
    }

    # Codex CLI can emit a clean JSON error event and exit nonzero without
    # producing a PowerShell exception. Inspect only top-level error events so
    # quoted historical messages inside command output cannot trigger this.
    if ($LogPath -and (Test-Path -LiteralPath $LogPath)) {
        foreach ($line in Get-Content -LiteralPath $LogPath -ErrorAction SilentlyContinue) {
            if (-not $line.StartsWith('{')) { continue }
            try {
                $event = $line | ConvertFrom-Json -ErrorAction Stop
                $eventMessage = ""
                if ($event.type -eq "error" -and $event.message) {
                    $eventMessage = [string]$event.message
                } elseif ($event.type -eq "turn.failed" -and $event.error -and $event.error.message) {
                    $eventMessage = [string]$event.error.message
                }
                foreach ($pattern in $usagePatterns) {
                    if ($eventMessage -match $pattern) { return $true }
                }
            } catch {
                # Partial JSONL is not treated as a usage-limit signal.
            }
        }
    }
    return $false
}

function Resolve-CodexExecutable {
    # A newly installed CLI may be present in the registry-backed user PATH
    # before the terminal host refreshes its inherited process PATH.
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathParts = @($env:PATH, $machinePath, $userPath) |
        Where-Object { $_ } |
        ForEach-Object { $_ -split ";" } |
        Where-Object { $_ } |
        Select-Object -Unique
    $env:PATH = $pathParts -join ";"

    foreach ($commandName in @("codex.exe", "codex")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandType -in @("Application", "ExternalScript") } |
            Select-Object -First 1
        if ($command) { return $command.Source }
    }

    # These cover the standalone Windows installer and the Codex Desktop bundle.
    $candidates = @(
        $env:CODEX_CLI_PATH,
        (Join-Path $env:LOCALAPPDATA "Programs\OpenAI\Codex\bin\codex.exe"),
        (Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin\codex.exe"),
        (Join-Path $env:USERPROFILE ".local\bin\codex.exe"),
        (Join-Path $env:USERPROFILE ".codex\bin\codex.exe")
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }

    $desktopBin = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
    if (Test-Path -LiteralPath $desktopBin) {
        $bundled = Get-ChildItem -LiteralPath $desktopBin -Filter "codex.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($bundled) { return $bundled.FullName }
    }

    return $null
}

$codexExe = Resolve-CodexExecutable
if (-not $codexExe) {
    throw "The Codex CLI could not be found. Open a new PowerShell window, or set CODEX_CLI_PATH to the full path of codex.exe, then rerun this script."
}

$codexVersion = (& $codexExe --version 2>&1 | Out-String).Trim()
Write-RunnerLog "Using $codexVersion from $codexExe"

if ($CheckOnly) {
    $checkMatrix = Get-LatestUatMatrix
    $checkUntested = Get-UntestedCount -Matrix $checkMatrix
    Write-RunnerLog "Latest matrix: $(if ($checkMatrix) { $checkMatrix.FullName } else { 'not found' })"
    Write-RunnerLog "Untested scenarios: $(if ($null -ne $checkUntested) { $checkUntested } else { 'unknown' })"
    Write-RunnerLog "Preflight passed. No Codex agent was started."
    return
}

if ($ResetSession -and (Test-Path -LiteralPath $statePath)) {
    Remove-Item -LiteralPath $statePath -Force
    Write-RunnerLog "Cleared the dedicated UAT Codex session."
}

$state = Read-RunnerState
$sessionId = if ($state -and $state.session_id) { [string]$state.session_id } else { $null }
$attempt = if ($state -and $state.attempt) { [int]$state.attempt } else { 0 }

Write-RunnerLog "TouchGrass UAT continuation runner started."
Write-RunnerLog "Polling interval: $IntervalMinutes minute(s). Press Ctrl+C to stop."
Write-RunnerLog "Create $stopPath to stop cleanly after the current attempt."

while ($true) {
    if (Test-Path -LiteralPath $stopPath) {
        Write-RunnerLog "STOP file detected. Exiting without starting another Codex run."
        break
    }

    $matrix = Get-LatestUatMatrix
    $untested = Get-UntestedCount -Matrix $matrix
    if ($null -ne $untested -and $untested -eq 0) {
        Write-RunnerLog "The latest consolidated matrix has zero Untested scenarios. UAT continuation is complete."
        break
    }

    if ($MaxAttempts -gt 0 -and $attempt -ge $MaxAttempts) {
        Write-RunnerLog "Reached MaxAttempts=$MaxAttempts."
        break
    }

    $attempt++
    $runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logPath = Join-Path $automationRoot ("attempt-{0:D4}-{1}.jsonl" -f $attempt, $runStamp)
    $lastMessagePath = Join-Path $automationRoot ("attempt-{0:D4}-{1}-last-message.txt" -f $attempt, $runStamp)
    $matrixPath = if ($matrix) { $matrix.FullName } else { "No consolidated matrix exists yet" }
    $remainingText = if ($null -ne $untested) { "$untested" } else { "unknown" }

    $prompt = @"
Continue the isolated TouchGrass UAT program from the repository root.

Current matrix: $matrixPath
Currently reported Untested scenarios: $remainingText

This invocation is one bounded unattended UAT batch. Follow these rules exactly:
1. Use only the isolated UAT frontend/backend on localhost ports 8115 and 8116. Never access or mutate development ports 8015/8016.
2. Do not edit application source code and do not fix defects. This is black-box testing and evidence collection only.
3. Read uat/scenarios.json, the six charter files under uat/, the latest consolidated matrix, and existing findings before choosing work.
4. Select a small coherent set of scenarios currently marked Untested. Prefer critical scenarios, then high priority. Do not rerun fully evidenced Pass scenarios unless needed to verify a dependency.
5. Verify Docker/UAT health before testing. Never mount or access real iCloud photos, real integration credentials, or live external services.
6. Use the generated UAT accounts and sanitized fixtures only. Never print credentials into reports or terminal output.
7. Capture reproducible evidence beneath the latest UAT run directory. Every defect needs severity, exact steps, expected/actual behavior, reproduction count, and relevant screenshot/network/log evidence when available.
8. Do not promote partial smoke coverage to Pass. Mark a scenario Pass only when its complete required behavior has direct evidence. Otherwise use Fail, Blocked, or Untested honestly.
9. Update the consolidated 44-scenario matrix and charter totals using evidence from this batch. Preserve earlier valid evidence and finding links. Re-read the matrix immediately before editing it; if patch context has drifted, retry with smaller targeted edits instead of abandoning the batch.
10. Stop the batch after meaningful progress or when a genuine blocker prevents further safe work. Summarize what ran, what changed in UAT data, and the next Untested scenario IDs.

If interactive browser tooling is unavailable, do not pretend UI scenarios passed. Run only scenarios that can be validly exercised with available black-box tools, record the tooling limitation, and leave unsupported scenarios Untested.
"@

    $codexArgs = @()
    if ($sessionId) {
        # Resume keeps the dedicated session's sandbox/approval configuration.
        $codexArgs += @("exec", "resume", "--json")
        if ($Model) { $codexArgs += @("--model", $Model) }
        $codexArgs += @("--output-last-message", $lastMessagePath, $sessionId, "-")
        Write-RunnerLog "Attempt ${attempt}: resuming dedicated session $sessionId."
    } else {
        # --approve-for-me already runs through the managed workspace-write
        # sandbox in Codex CLI 0.152+, so it must not be combined with --sandbox.
        $codexArgs += @("exec", "--json", "--approve-for-me", "--cd", $projectRoot)
        if ($Model) { $codexArgs += @("--model", $Model) }
        $codexArgs += @("--output-last-message", $lastMessagePath, "-")
        Write-RunnerLog "Attempt ${attempt}: creating a dedicated UAT session."
    }

    $exitCode = 1
    $invocationFailureText = ""
    try {
        $prompt | & $codexExe @codexArgs 2>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    } catch {
        $invocationFailureText = $_ | Out-String
        $invocationFailureText | Add-Content -LiteralPath $logPath
        Write-Warning "Codex invocation failed: $($_.Exception.Message)"
    }

    if (-not $sessionId) {
        $sessionId = Find-SessionId -LogPath $logPath
        if ($sessionId) {
            Write-RunnerLog "Captured dedicated session $sessionId for future attempts."
        } else {
            Write-Warning "No Codex session ID was found. The next attempt will start a fresh session."
        }
    }

    $sessionWasCorrupt = Test-CorruptCodexSession -LogPath $logPath -InvocationFailureText $invocationFailureText
    $usageLimitReached = Test-CodexUsageLimit -InvocationFailureText $invocationFailureText -LogPath $logPath
    if ($sessionWasCorrupt) {
        $discardedSession = $sessionId
        $sessionId = $null
        Write-Warning "Codex session state is corrupted by a missing tool-call result. Discarding dedicated session $discardedSession; UAT progress remains preserved in the artifact matrix."
    }

    Save-RunnerState -SessionId $sessionId -Attempt $attempt -ExitCode $exitCode -LogPath $logPath

    $matrix = Get-LatestUatMatrix
    $untested = Get-UntestedCount -Matrix $matrix
    if ($null -ne $untested -and $untested -eq 0) {
        Write-RunnerLog "The consolidated matrix is complete after attempt $attempt."
        break
    }

    if ($exitCode -eq 0) {
        Write-RunnerLog "Attempt $attempt finished. Remaining Untested count: $(if ($null -ne $untested) { $untested } else { 'unknown' })."
    } else {
        Write-RunnerLog "Attempt $attempt exited with code $exitCode. This may be a usage limit, network problem, or agent failure; it will be retried."
    }

    if ($Once) {
        Write-RunnerLog "-Once was specified. Exiting."
        break
    }

    if ($sessionWasCorrupt) {
        Write-RunnerLog "Waiting 30 seconds, then starting a fresh dedicated session automatically."
        Start-Sleep -Seconds 30
    } elseif ($exitCode -ne 0 -and -not $usageLimitReached) {
        Write-RunnerLog "The session was retained. Waiting 60 seconds for a quick recovery attempt instead of the normal polling interval."
        Start-Sleep -Seconds 60
    } else {
        Write-RunnerLog "Waiting $IntervalMinutes minute(s) before the next attempt."
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}
