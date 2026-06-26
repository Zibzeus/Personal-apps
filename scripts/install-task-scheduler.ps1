$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$WebScript = Join-Path $Root "scripts\start-web.ps1"
$BotScript = Join-Path $Root "scripts\start-bot.ps1"

$ActionWeb = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WebScript`""
$ActionBot = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$BotScript`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "MoneyManagerWeb" -Action $ActionWeb -Trigger $Trigger -Settings $Settings -Description "Start local Money Manager dashboard" -Force
Register-ScheduledTask -TaskName "MoneyManagerBot" -Action $ActionBot -Trigger $Trigger -Settings $Settings -Description "Start Money Manager Telegram bot" -Force

Write-Host "Installed scheduled tasks: MoneyManagerWeb and MoneyManagerBot."

