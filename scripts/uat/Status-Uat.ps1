[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "Uat.Common.ps1")

try {
    Assert-DockerHealthy
} catch {
    Write-Host "Docker: unavailable"
    Write-Host $_.Exception.Message
    exit 1
}

Initialize-UatEnvironment
Write-Host "Docker: running"
Write-Host "Compose project: $script:UatProject"
Write-Host "Network isolation: UAT-only bridge network"
Write-Host "Frontend: http://localhost:8115"
Write-Host "Backend:  http://localhost:8116"

$currentRunFile = Join-Path $script:UatArtifacts "current-run.txt"
if (Test-Path $currentRunFile) {
    Write-Host "Current run: $((Get-Content $currentRunFile -Raw).Trim())"
} else {
    Write-Host "Current run: not initialized"
}

Write-Host ""
Invoke-UatCompose -Arguments @("ps")

foreach ($check in @(
    @{ Name = "Frontend"; Url = "http://localhost:8115/login" },
    @{ Name = "Backend"; Url = "http://localhost:8116/csrf/" }
)) {
    try {
        $response = Invoke-WebRequest -Uri $check.Url -UseBasicParsing -TimeoutSec 5
        Write-Host "$($check.Name) HTTP: $($response.StatusCode)"
    } catch {
        Write-Host "$($check.Name) HTTP: unavailable"
    }
}

if (
    (Test-Path (Join-Path $script:UatArtifacts "baseline\uat-baseline.dump")) -and
    (Test-Path (Join-Path $script:UatArtifacts "baseline\uat-media.tar"))
) {
    Write-Host "Reset baseline: available"
} else {
    Write-Host "Reset baseline: missing"
}
