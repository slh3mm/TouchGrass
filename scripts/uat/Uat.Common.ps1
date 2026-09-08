Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:UatRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:UatComposeFile = Join-Path $script:UatRoot "docker-compose.uat.yml"
$script:UatEnvExample = Join-Path $script:UatRoot ".env.uat.example"
$script:UatEnvLocal = Join-Path $script:UatRoot ".env.uat.local"
$script:UatArtifacts = Join-Path $script:UatRoot ".uat-artifacts"
$script:UatProject = "touchgrass-uat"

function Invoke-DockerChecked {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed (exit $LASTEXITCODE): docker $($Arguments -join ' ')"
    }
}

function Invoke-UatCompose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $composeArguments = @(
        "compose",
        "--project-name", $script:UatProject,
        "--env-file", $script:UatEnvLocal,
        "--file", $script:UatComposeFile
    ) + $Arguments
    Invoke-DockerChecked -Arguments $composeArguments
}

function Get-UatContainerId {
    param([Parameter(Mandatory = $true)][string]$Service)

    $arguments = @(
        "compose",
        "--project-name", $script:UatProject,
        "--env-file", $script:UatEnvLocal,
        "--file", $script:UatComposeFile,
        "ps", "--quiet", $Service
    )
    $result = @(& docker @arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to find the UAT $Service container."
    }
    $containerId = (($result | Select-Object -Last 1) -as [string])
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "The UAT $Service container is not running."
    }
    return $containerId.Trim()
}

function Assert-DockerHealthy {
    & docker info --format "{{.ServerVersion}}" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop's Linux engine is not running. Start Docker Desktop and wait for 'Engine running', then retry."
    }
}

function New-RandomHex {
    param([int]$Bytes = 32)

    $buffer = New-Object byte[] $Bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($buffer)
    } finally {
        $generator.Dispose()
    }
    return ([BitConverter]::ToString($buffer)).Replace("-", "").ToLowerInvariant()
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Initialize-UatEnvironment {
    if (-not (Test-Path $script:UatEnvLocal)) {
        $template = Get-Content $script:UatEnvExample -Raw
        $template = $template.Replace("POSTGRES_PASSWORD=uat-example-only", "POSTGRES_PASSWORD=$(New-RandomHex 24)")
        $template = $template.Replace("SECRET_KEY=uat-example-only", "SECRET_KEY=$(New-RandomHex 48)")
        $template = $template.Replace("UAT_OWNER_PASSWORD=uat-example-only", "UAT_OWNER_PASSWORD=Uat-$(New-RandomHex 12)")
        $template = $template.Replace("UAT_MEMBER_PASSWORD=uat-example-only", "UAT_MEMBER_PASSWORD=Uat-$(New-RandomHex 12)")
        $template = $template.Replace("UAT_OUTSIDER_PASSWORD=uat-example-only", "UAT_OUTSIDER_PASSWORD=Uat-$(New-RandomHex 12)")
        $template = $template.Replace("UAT_EMPTY_PASSWORD=uat-example-only", "UAT_EMPTY_PASSWORD=Uat-$(New-RandomHex 12)")
        Write-Utf8NoBom -Path $script:UatEnvLocal -Content $template
    }

    New-Item -ItemType Directory -Force -Path $script:UatArtifacts | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $script:UatArtifacts "baseline") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $script:UatArtifacts "private") | Out-Null

    $syntheticMedia = Join-Path $script:UatArtifacts "synthetic-media"
    New-Item -ItemType Directory -Force -Path $syntheticMedia | Out-Null
    $placeholder = Join-Path $syntheticMedia "uat-placeholder.png"
    if (-not (Test-Path $placeholder)) {
        # Transparent 1x1 PNG. It is deliberately synthetic and contains no user media.
        $png = [Convert]::FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL+WQAAAABJRU5ErkJggg==")
        [IO.File]::WriteAllBytes($placeholder, $png)
    }
}

function Get-UatEnvironment {
    $values = @{}
    foreach ($line in Get-Content $script:UatEnvLocal) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $value = $line -split '=', 2
        $values[$key.Trim()] = $value.Trim()
    }
    return $values
}

function New-UatRun {
    param([string]$Prefix = "run")

    $runId = "{0}-{1}" -f $Prefix, ([DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss"))
    $runPath = Join-Path $script:UatArtifacts $runId
    foreach ($directory in @("screenshots", "console", "network", "backend-logs", "agent-reports")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $runPath $directory) | Out-Null
    }
    Write-Utf8NoBom -Path (Join-Path $script:UatArtifacts "current-run.txt") -Content $runId
    return @{ Id = $runId; Path = $runPath }
}

function Wait-UatDatabase {
    param([int]$TimeoutSeconds = 120)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        & docker compose --project-name $script:UatProject --env-file $script:UatEnvLocal --file $script:UatComposeFile exec -T db sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' *> $null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "The UAT database did not become ready within $TimeoutSeconds seconds."
}

function Wait-UatHttp {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 180
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
        } catch {
            # Startup failures are reported with container logs after the deadline.
        }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "$Url did not become available within $TimeoutSeconds seconds. Run scripts/uat/Status-Uat.ps1 for diagnostics."
}

function Reset-UatDatabaseFromDump {
    param([Parameter(Mandatory = $true)][string]$DumpPath)

    if (-not (Test-Path $DumpPath)) { throw "Database dump not found: $DumpPath" }
    Invoke-UatCompose -Arguments @("stop", "web", "server")
    Invoke-UatCompose -Arguments @("up", "--detach", "db")
    Wait-UatDatabase

    $dbContainer = Get-UatContainerId -Service "db"
    Invoke-DockerChecked -Arguments @("cp", $DumpPath, "${dbContainer}:/tmp/touchgrass-uat.dump")
    Invoke-UatCompose -Arguments @(
        "exec", "-T", "db", "sh", "-ec",
        'export PGPASSWORD="$POSTGRES_PASSWORD"; dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"; createdb -U "$POSTGRES_USER" "$POSTGRES_DB"; pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/touchgrass-uat.dump; rm -f /tmp/touchgrass-uat.dump'
    )
}

function Save-UatMediaBaseline {
    $mediaArchive = "/uat-artifacts/baseline/uat-media.tar"
    Invoke-UatCompose -Arguments @(
        "exec", "-T", "server", "sh", "-ec",
        "rm -f $mediaArchive; tar -C /code/media -cf $mediaArchive ."
    )
}

function Restore-UatMediaBaseline {
    $mediaArchive = Join-Path $script:UatArtifacts "baseline\uat-media.tar"
    if (-not (Test-Path $mediaArchive)) { throw "Media baseline not found: $mediaArchive" }

    # This one-off container receives only the UAT media/cache volumes. Its
    # explicit mount paths prevent the reset from reaching host or dev media.
    Invoke-UatCompose -Arguments @(
        "run", "--rm", "--no-deps", "--entrypoint", "sh", "server", "-ec",
        'find /code/media -mindepth 1 -delete; tar -C /code/media -xf /uat-artifacts/baseline/uat-media.tar; find /code/photo-previews -mindepth 1 -delete'
    )
}

function Write-UatCredentials {
    param([Parameter(Mandatory = $true)][hashtable]$Environment)

    $credentials = [ordered]@{
        notice = "Local UAT credentials. Never commit or share this file."
        frontend_url = "http://localhost:8115"
        accounts = [ordered]@{
            owner = @{ username = "uat-owner"; password = $Environment["UAT_OWNER_PASSWORD"] }
            member = @{ username = "uat-member"; password = $Environment["UAT_MEMBER_PASSWORD"] }
            outsider = @{ username = "uat-outsider"; password = $Environment["UAT_OUTSIDER_PASSWORD"] }
            empty = @{ username = "uat-empty"; password = $Environment["UAT_EMPTY_PASSWORD"] }
        }
    }
    $path = Join-Path $script:UatArtifacts "private\credentials.json"
    Write-Utf8NoBom -Path $path -Content ($credentials | ConvertTo-Json -Depth 5)
}
