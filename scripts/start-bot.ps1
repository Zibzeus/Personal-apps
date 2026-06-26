$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "runtime\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

& $Python (Join-Path $Root "manage.py") runbot 2>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "bot.log")

