param(
    [string]$BackupDir = "",
    [switch]$KeepContainer,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Checks = New-Object System.Collections.Generic.List[object]

if (-not $BackupDir) {
    $BackupDir = Join-Path $RepoRoot "backups\restore-drills"
}

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message
    )
    $Checks.Add([pscustomobject]@{
        name = $Name
        status = $Status
        message = $Message
    }) | Out-Null
}

function Get-RootEnvValue {
    param([string]$Name)

    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) {
        return $null
    }

    $line = Get-Content $envFile | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    $value = ($line -split "=", 2)[1].Trim()
    return $value.Trim("'").Trim('"')
}

function Invoke-Docker {
    param([string[]]$Arguments)

    $output = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join "`n")
    }
    return $output
}

Push-Location $RepoRoot
try {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    $backupFile = Join-Path $BackupDir "edq_restore_drill_$Timestamp.sql"
    $evidenceFile = Join-Path $BackupDir "edq_restore_drill_$Timestamp.json"
    $sourceContainer = ((& docker compose ps -q postgres) -join "").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $sourceContainer) {
        throw "The postgres service is not running. Start EDQ with docker compose up -d first."
    }
    Add-Check "Source postgres" "ok" "Found running postgres container $sourceContainer."

    $tmpDump = "/tmp/edq_restore_drill_$Timestamp.sql"
    $dumpCommand = "set -e; export PGPASSWORD=`"`$POSTGRES_PASSWORD`"; pg_dump -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -f `"$tmpDump`"; test -s `"$tmpDump`"; wc -c < `"$tmpDump`""
    $dumpSize = ((Invoke-Docker @("compose", "exec", "-T", "postgres", "sh", "-lc", $dumpCommand)) -join "").Trim()
    Add-Check "Backup dump" "ok" "Created dump inside source container ($dumpSize bytes)."

    Invoke-Docker @("cp", "${sourceContainer}:$tmpDump", $backupFile) | Out-Null
    Invoke-Docker @("compose", "exec", "-T", "postgres", "rm", "-f", $tmpDump) | Out-Null
    if (-not (Test-Path $backupFile) -or ((Get-Item $backupFile).Length -le 0)) {
        throw "Backup file was not copied or is empty."
    }
    Add-Check "Backup file" "ok" "Saved $backupFile."

    $dbName = Get-RootEnvValue "DB_NAME"
    if (-not $dbName) { $dbName = "edq" }
    $dbUser = Get-RootEnvValue "DB_USER"
    if (-not $dbUser) { $dbUser = "edq" }
    $dbPassword = Get-RootEnvValue "POSTGRES_PASSWORD"
    if (-not $dbPassword) { throw "POSTGRES_PASSWORD is required in .env." }

    $containerName = "edq-restore-drill-$Timestamp"
    Invoke-Docker @(
        "run", "-d",
        "--name", $containerName,
        "-e", "POSTGRES_DB=$dbName",
        "-e", "POSTGRES_USER=$dbUser",
        "-e", "POSTGRES_PASSWORD=$dbPassword",
        "edq-postgres"
    ) | Out-Null
    Add-Check "Drill postgres" "ok" "Started disposable restore container $containerName."

    $ready = $false
    for ($attempt = 1; $attempt -le 30 -and -not $ready; $attempt++) {
        & docker exec $containerName pg_isready -U $dbUser -d $dbName *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
        } else {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        throw "Disposable restore database did not become ready."
    }
    Add-Check "Drill readiness" "ok" "Disposable PostgreSQL is accepting connections."

    Invoke-Docker @("cp", $backupFile, "${containerName}:/tmp/restore.sql") | Out-Null
    Invoke-Docker @("exec", $containerName, "sh", "-lc", "psql -U `"$dbUser`" -d `"$dbName`" -v ON_ERROR_STOP=1 -f /tmp/restore.sql >/tmp/restore.log") | Out-Null
    Add-Check "Restore" "ok" "Backup restored into disposable PostgreSQL container."

    $verifySql = "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') AS tables, (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM authorized_networks) AS authorized_networks, (SELECT count(*) FROM test_templates) AS test_templates;"
    $verify = ((Invoke-Docker @("exec", $containerName, "psql", "-U", $dbUser, "-d", $dbName, "-At", "-F", ",", "-c", $verifySql)) -join "").Trim()
    $parts = $verify.Split(",")
    if ($parts.Count -ne 4 -or [int]$parts[0] -lt 10 -or [int]$parts[1] -lt 1 -or [int]$parts[3] -lt 1) {
        throw "Restore verification returned unexpected counts: $verify"
    }
    Add-Check "Data verification" "ok" "tables=$($parts[0]), users=$($parts[1]), authorized_networks=$($parts[2]), test_templates=$($parts[3])."

    $evidence = [pscustomobject]@{
        status = "ok"
        generated_at = (Get-Date).ToString("o")
        backup_file = $backupFile
        restore_container = $containerName
        verification = @{
            tables = [int]$parts[0]
            users = [int]$parts[1]
            authorized_networks = [int]$parts[2]
            test_templates = [int]$parts[3]
        }
        checks = $Checks
    }
    $evidence | ConvertTo-Json -Depth 6 | Set-Content -Path $evidenceFile -Encoding UTF8
    Add-Check "Evidence file" "ok" "Saved $evidenceFile."
} catch {
    Add-Check "Restore drill" "error" $_.Exception.Message
} finally {
    if ($containerName -and -not $KeepContainer) {
        & docker rm -f $containerName *> $null
    }
    Pop-Location
}

if ($Json) {
    $Checks | ConvertTo-Json -Depth 5
} else {
    Write-Host ""
    Write-Host "EDQ backup restore drill"
    Write-Host ""
    foreach ($check in $Checks) {
        $color = switch ($check.status) {
            "error" { "Red" }
            "warning" { "Yellow" }
            default { "Green" }
        }
        Write-Host ("[{0}] {1}: {2}" -f $check.status.ToUpperInvariant(), $check.name, $check.message) -ForegroundColor $color
    }
}

if (@($Checks | Where-Object { $_.status -eq "error" }).Count -gt 0) {
    exit 1
}
