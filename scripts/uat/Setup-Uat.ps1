[CmdletBinding()]
param(
    [switch]$Fresh,
    [ValidateSet("core", "stress", "all")][string]$Scenario = "all",
    [string]$AnchorDate = "2026-08-11",
    [string]$SourceOwnerUsername = ""
)

. (Join-Path $PSScriptRoot "Uat.Common.ps1")

Assert-DockerHealthy
Initialize-UatEnvironment
$environment = Get-UatEnvironment
$run = New-UatRun -Prefix "setup"
$sourceDump = Join-Path $run.Path "development-source.dump"

Write-Host "Preparing isolated TouchGrass UAT on http://localhost:8115 ..."
Invoke-UatCompose -Arguments @("config", "--quiet")
Invoke-UatCompose -Arguments @("stop", "web", "server")
Invoke-UatCompose -Arguments @("up", "--detach", "db")
Wait-UatDatabase

if (-not $Fresh) {
    $devCompose = Join-Path $script:UatRoot "docker-compose.dev.yml"
    $devDbResult = @(& docker compose --file $devCompose ps --quiet db)
    if ($LASTEXITCODE -ne 0) { throw "Unable to inspect the development database container." }
    $devDb = (($devDbResult | Select-Object -Last 1) -as [string]).Trim()
    if ([string]::IsNullOrWhiteSpace($devDb)) {
        throw "The development database is not running. Start it first, or rerun Setup-Uat.ps1 -Fresh for synthetic-only UAT data."
    }

    try {
        Write-Host "Copying the development database into a temporary local dump ..."
        try {
            Invoke-DockerChecked -Arguments @(
                "exec", $devDb, "sh", "-ec",
                'rm -f /tmp/touchgrass-uat-source.dump; PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --file=/tmp/touchgrass-uat-source.dump'
            )
            Invoke-DockerChecked -Arguments @("cp", "${devDb}:/tmp/touchgrass-uat-source.dump", $sourceDump)
        } finally {
            & docker exec $devDb rm -f /tmp/touchgrass-uat-source.dump *> $null
        }
        Reset-UatDatabaseFromDump -DumpPath $sourceDump
    } finally {
        if (Test-Path $sourceDump) { Remove-Item -LiteralPath $sourceDump -Force }
    }
} else {
    Write-Host "Creating a fresh UAT database with synthetic fixtures only ..."
    Invoke-UatCompose -Arguments @(
        "exec", "-T", "db", "sh", "-ec",
        'export PGPASSWORD="$POSTGRES_PASSWORD"; dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"; createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
    )
}

try {
    Invoke-UatCompose -Arguments @("up", "--build", "--detach", "server")
    Wait-UatHttp -Url "http://localhost:8116/csrf/"

    $manifestInContainer = "/uat-artifacts/$($run.Id)/manifest.json"
    $prepareArguments = @(
        "exec", "-T", "server", "python", "manage.py", "prepare_uat",
        "--manifest", $manifestInContainer,
        "--reset",
        "--anchor-date", $AnchorDate,
        "--scenario", $Scenario
    )
    if (-not $Fresh -and -not [string]::IsNullOrWhiteSpace($SourceOwnerUsername)) {
        $prepareArguments += @("--owner-username", $SourceOwnerUsername)
    }
    Invoke-UatCompose -Arguments $prepareArguments

    $manifest = Join-Path $run.Path "manifest.json"
    if (-not (Test-Path $manifest)) {
        throw "prepare_uat completed without producing the expected manifest: $manifest"
    }
} catch {
    $setupError = $_
    Write-Warning "UAT preparation failed. Removing the unsanitized database copy and stopping application services."
    try {
        Invoke-UatCompose -Arguments @("stop", "web", "server")
        Invoke-UatCompose -Arguments @(
            "exec", "-T", "db", "sh", "-ec",
            'export PGPASSWORD="$POSTGRES_PASSWORD"; dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"; createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
        )
    } catch {
        Write-Warning "Automatic UAT database cleanup also failed. Keep UAT stopped and inspect Docker before retrying."
    }
    throw $setupError
}

Write-Host "Capturing the scrubbed, deterministic reset baseline ..."
$dbContainer = Get-UatContainerId -Service "db"
$baselineDump = Join-Path $script:UatArtifacts "baseline\uat-baseline.dump"
try {
    Invoke-DockerChecked -Arguments @(
        "exec", $dbContainer, "sh", "-ec",
        'rm -f /tmp/touchgrass-uat-baseline.dump; PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --file=/tmp/touchgrass-uat-baseline.dump'
    )
    Invoke-DockerChecked -Arguments @("cp", "${dbContainer}:/tmp/touchgrass-uat-baseline.dump", $baselineDump)
} finally {
    & docker exec $dbContainer rm -f /tmp/touchgrass-uat-baseline.dump *> $null
}
Copy-Item -LiteralPath $manifest -Destination (Join-Path $script:UatArtifacts "baseline\manifest.json") -Force
Save-UatMediaBaseline
Write-UatCredentials -Environment $environment

Invoke-UatCompose -Arguments @("up", "--build", "--detach", "web")
Wait-UatHttp -Url "http://localhost:8115/login"

Write-Host ""
Write-Host "UAT is ready: http://localhost:8115"
Write-Host "Run ID: $($run.Id)"
Write-Host "Sanitized manifest: $manifest"
Write-Host "Local credentials: .uat-artifacts/private/credentials.json"
Write-Host "Development remains isolated on its existing ports and volumes."
