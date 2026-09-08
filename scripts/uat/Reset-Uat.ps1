[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "Uat.Common.ps1")

Assert-DockerHealthy
Initialize-UatEnvironment
$baselineDump = Join-Path $script:UatArtifacts "baseline\uat-baseline.dump"
$baselineManifest = Join-Path $script:UatArtifacts "baseline\manifest.json"
$baselineMedia = Join-Path $script:UatArtifacts "baseline\uat-media.tar"
if (-not (Test-Path $baselineDump) -or -not (Test-Path $baselineManifest) -or -not (Test-Path $baselineMedia)) {
    throw "No UAT baseline exists. Run scripts/uat/Setup-Uat.ps1 first."
}

$run = New-UatRun -Prefix "reset"
Write-Host "Restoring the isolated UAT database baseline ..."
Reset-UatDatabaseFromDump -DumpPath $baselineDump
Restore-UatMediaBaseline
Copy-Item -LiteralPath $baselineManifest -Destination (Join-Path $run.Path "manifest.json") -Force

Invoke-UatCompose -Arguments @("up", "--build", "--detach", "server")
Wait-UatHttp -Url "http://localhost:8116/csrf/"
Invoke-UatCompose -Arguments @("up", "--build", "--detach", "web")
Wait-UatHttp -Url "http://localhost:8115/login"

Write-Host "UAT baseline restored."
Write-Host "Run ID: $($run.Id)"
Write-Host "UAT URL: http://localhost:8115"
