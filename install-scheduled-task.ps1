# Install Ryuu K Watchdog as a Windows Scheduled Task
# Run this PowerShell script as Administrator

$botDir = 'C:\Users\EliteBook\OneDrive\Ryuu\GPT docs\Ryuu_RAG\discord-rag-bot'
$watchdogDir = Join-Path $botDir 'watchdog'
$scriptPath = Join-Path $watchdogDir 'watchdog.py'
$pythonExe = (Get-Command python).Source
$taskName = 'RyuuK-Watchdog'

if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Error "watchdog.py not found at $scriptPath"
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath -WorkingDirectory $watchdogDir

# Start at logon of any user, restart every 5 minutes if it fails
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

# Run whether user is logged on or not, with highest privileges
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

Write-Output "Scheduled task '$taskName' installed. It will start automatically at logon."
Write-Output "To start it now: Start-ScheduledTask -TaskName '$taskName'"
Write-Output "To check status: Get-ScheduledTask -TaskName '$taskName'"
