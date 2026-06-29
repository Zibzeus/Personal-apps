param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
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

$BotEnabled = Get-LocalEnvValue "TELEGRAM_BOT_ENABLED" "0"
if (-not $Force -and $BotEnabled -ne "1") {
    Write-Host "Money Manager Telegram bot is disabled. Set TELEGRAM_BOT_ENABLED=1 or run this script with -Force to start it."
    exit 0
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "runtime\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

& $Python (Join-Path $Root "manage.py") runbot 2>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "bot.log")

