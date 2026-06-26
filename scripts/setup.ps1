$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not (Test-Path -LiteralPath $Venv)) {
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Checked { & $Python -m pip install --upgrade pip }
Invoke-Checked { & $Python -m pip install -r (Join-Path $Root "requirements.txt") }

$EnvFile = Join-Path $Root ".env"
$Example = Join-Path $Root ".env.example"
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath $Example -Destination $EnvFile
    Write-Host "Created .env. Fill TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS before starting the bot."
}

Invoke-Checked { & $Python (Join-Path $Root "manage.py") migrate }
Invoke-Checked { & $Python (Join-Path $Root "manage.py") seed_defaults }

Write-Host "Setup complete."
