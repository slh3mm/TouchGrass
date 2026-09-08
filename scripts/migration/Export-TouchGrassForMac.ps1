[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.dev.yml",
    [string]$OutputRoot = ".migration-exports",
    [switch]$IncludeSecrets,
    [switch]$SkipUatArtifacts
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
Set-Location -LiteralPath $repoRoot

function Invoke-Native {
    param([scriptblock]$Command, [string]$FailureMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    throw "Compose file not found: $ComposeFile"
}

Invoke-Native { docker info --format '{{.ServerVersion}}' | Out-Null } "Docker is not available"

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedOutputRoot = Join-Path $repoRoot $OutputRoot
$bundleName = "touchgrass-mac-transfer-$stamp"
$stage = Join-Path $resolvedOutputRoot $bundleName
$archive = "$stage.zip"

New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage "private") | Out-Null

Write-Host "Creating portable PostgreSQL dump..."
$dbId = (& docker compose -f $ComposeFile ps -q db).Trim()
if (-not $dbId) {
    throw "The Compose database service is not running. Start it before exporting."
}

Invoke-Native {
    docker compose -f $ComposeFile exec -T db sh -lc 'rm -f /tmp/touchgrass-mac-transfer.dump && PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges --file=/tmp/touchgrass-mac-transfer.dump'
} "PostgreSQL export failed"
Invoke-Native {
    docker cp "${dbId}:/tmp/touchgrass-mac-transfer.dump" (Join-Path $stage "touchgrass-postgres.dump")
} "Could not copy the PostgreSQL dump from Docker"
Invoke-Native {
    docker compose -f $ComposeFile exec -T db rm -f /tmp/touchgrass-mac-transfer.dump
} "Could not remove the temporary database dump inside Docker"

Write-Host "Archiving AdventureLog media..."
$serverId = (& docker compose -f $ComposeFile ps -q server).Trim()
if (-not $serverId) {
    throw "The Compose backend service is not running. Start it before exporting media."
}
if ($IncludeSecrets) {
    Invoke-Native {
        docker compose -f $ComposeFile exec -T server sh -lc 'rm -f /tmp/touchgrass-media.tar.gz && tar -czf /tmp/touchgrass-media.tar.gz -C /code/media .'
    } "Media archive failed"
} else {
    Invoke-Native {
        docker compose -f $ComposeFile exec -T server sh -lc 'rm -f /tmp/touchgrass-media.tar.gz && tar --exclude=./.skylight-credential-key --exclude=.skylight-credential-key -czf /tmp/touchgrass-media.tar.gz -C /code/media .'
    } "Media archive failed"
}
Invoke-Native {
    docker cp "${serverId}:/tmp/touchgrass-media.tar.gz" (Join-Path $stage "touchgrass-media.tar.gz")
} "Could not copy the media archive from Docker"
Invoke-Native {
    docker compose -f $ComposeFile exec -T server rm -f /tmp/touchgrass-media.tar.gz
} "Could not remove the temporary media archive inside Docker"

if (-not $SkipUatArtifacts -and (Test-Path -LiteralPath ".uat-artifacts")) {
    Write-Host "Archiving ignored UAT evidence..."
    Invoke-Native {
        tar.exe -czf (Join-Path $stage "touchgrass-uat-artifacts.tar.gz") .uat-artifacts
    } "UAT evidence archive failed"
}

$secretFiles = @(".env", ".env.uat.local")
if ($IncludeSecrets) {
    Write-Warning "The transfer bundle will contain plaintext environment secrets. Keep it off GitHub and use a private transfer channel."
    foreach ($secretFile in $secretFiles) {
        if (Test-Path -LiteralPath $secretFile) {
            Copy-Item -LiteralPath $secretFile -Destination (Join-Path $stage "private")
        }
    }
} else {
    @"
Environment files were deliberately excluded.

Create .env on the Mac from .env.example, use new strong secrets, and reconnect integrations.
If preserving the exact Django/Skylight encryption keys is required, rerun this exporter with
-IncludeSecrets and transfer the resulting archive privately. Never commit that archive.
"@ | Set-Content -LiteralPath (Join-Path $stage "private\SECRETS_NOT_INCLUDED.txt") -Encoding UTF8
}

$gitCommit = (& git rev-parse HEAD).Trim()
$gitBranch = (& git branch --show-current).Trim()
$gitStatus = @(& git status --short)

$manifest = [ordered]@{
    format_version = 1
    created_at = (Get-Date).ToString("o")
    source_platform = "Windows"
    source_repository = $repoRoot
    git_commit = $gitCommit
    git_branch = $gitBranch
    working_tree_clean = ($gitStatus.Count -eq 0)
    compose_file = $ComposeFile
    includes_database = $true
    includes_media = $true
    includes_uat_artifacts = (Test-Path -LiteralPath (Join-Path $stage "touchgrass-uat-artifacts.tar.gz"))
    includes_secrets = [bool]$IncludeSecrets
    excluded = @(
        "Docker raw volumes and Docker Desktop VM disk",
        "photo preview cache",
        "node_modules and pnpm cache",
        "iCloud originals",
        "Windows DPAPI poller configuration",
        "Skylight media-volume credential key unless -IncludeSecrets is used"
    )
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stage "manifest.json") -Encoding UTF8
$gitStatus | Set-Content -LiteralPath (Join-Path $stage "git-status.txt") -Encoding UTF8

@"
# TouchGrass Mac transfer bundle

This bundle contains private travel data. Do not commit it or upload it to a public service.

Restore it from the cloned repository with:

    chmod +x scripts/migration/Restore-TouchGrassOnMac.sh
    scripts/migration/Restore-TouchGrassOnMac.sh /path/to/$bundleName.zip

Read MAC_HANDOFF.md and documentation/docs/development/macos_setup.md first.
"@ | Set-Content -LiteralPath (Join-Path $stage "README.md") -Encoding UTF8

$hashTargets = Get-ChildItem -LiteralPath $stage -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" }
$hashLines = foreach ($file in $hashTargets) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    "$hash  $($file.Name)"
}
$hashLines | Set-Content -LiteralPath (Join-Path $stage "SHA256SUMS.txt") -Encoding ASCII

if (Test-Path -LiteralPath $archive) {
    throw "Refusing to overwrite existing archive: $archive"
}
Compress-Archive -LiteralPath $stage -DestinationPath $archive -CompressionLevel Optimal

$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
Write-Host ""
Write-Host "Export complete: $archive"
Write-Host "SHA-256: $archiveHash"
Write-Host "Secrets included: $([bool]$IncludeSecrets)"
Write-Host "Keep this archive private and do not add it to Git."
