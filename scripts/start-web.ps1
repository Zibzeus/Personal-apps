$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

function Get-LocalEnvValue {
    param(
        [string]$Key,
        [string]$Default
    )
    $ProcessValue = [Environment]::GetEnvironmentVariable($Key, "Process")
    if ($ProcessValue) {
        return $ProcessValue
    }
    if (Test-Path -LiteralPath $EnvFile) {
        foreach ($Line in Get-Content -LiteralPath $EnvFile) {
            if ($Line -match "^\s*$([regex]::Escape($Key))=(.*)$") {
                return $matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $Default
}

$HostName = Get-LocalEnvValue "WEB_HOST" "127.0.0.1"
$Port = Get-LocalEnvValue "WEB_PORT" "8000"
$LogDir = Join-Path $Root "runtime\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Checked { & $Python (Join-Path $Root "manage.py") migrate }
Invoke-Checked { & $Python (Join-Path $Root "manage.py") seed_defaults }

$LogFile = Join-Path $LogDir "web.log"
try {
    $LockProbe = [System.IO.File]::Open($LogFile, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
    $LockProbe.Close()
}
catch {
    $LogFile = Join-Path $LogDir ("web-{0}.log" -f $PID)
}

Write-Host "Money Manager dashboard is starting at http://$HostName`:$Port/"
Write-Host "Django server logs are written to $LogFile"
Write-Host "Press Ctrl+C to stop the dashboard."

$PreviousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $Manage = Join-Path $Root "manage.py"
    $RunCommand = "`"$Python`" `"$Manage`" runserver `"$HostName`:$Port`" --noreload >> `"$LogFile`" 2>&1"
    & cmd.exe /d /s /c $RunCommand
    $ExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}

if ($ExitCode -ne 0) {
    Write-Host "Dashboard stopped with exit code $ExitCode. Check $LogFile for details."
    exit $ExitCode
}
