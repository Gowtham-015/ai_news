# ============================================================================
# AI News Automation Agent - Windows Autostart & Task Scheduler Installer
# ============================================================================

$TaskName = "AI News Automation Agent"
$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) { $ProjectDir = Get-Location }

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " AI NEWS AUTOMATION AGENT - WINDOWS INSTALLER" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$PythonExe = Join-Path $ProjectDir "venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment Python not found in $ProjectDir" -ForegroundColor Red
    exit 1
}

$MainScript = Join-Path $ProjectDir "main.py"
if (-not (Test-Path $MainScript)) {
    Write-Host "[ERROR] main.py not found in $ProjectDir" -ForegroundColor Red
    exit 1
}

$LauncherBat = Join-Path $ProjectDir "start_agent.bat"
if (-not (Test-Path $LauncherBat)) {
    Write-Host "[ERROR] start_agent.bat not found in $ProjectDir" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Python Executable: $PythonExe" -ForegroundColor Green
Write-Host "[OK] Project Directory: $ProjectDir" -ForegroundColor Green
Write-Host "[OK] Launcher Script:   $LauncherBat" -ForegroundColor Green
Write-Host ""

# 1. Attempt Windows Scheduled Task creation
$TaskCreated = $false
try {
    $Action = New-ScheduledTaskAction -Execute $LauncherBat
    $Trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -ErrorAction Stop | Out-Null
    $TaskCreated = $true
    Write-Host "[OK] Registered Windows Scheduled Task: '$TaskName'" -ForegroundColor Green
} catch {
    Write-Host "[INFO] Standard user environment detected. Installing Windows Startup Folder shortcut..." -ForegroundColor Yellow
}

# 2. Register Startup Folder shortcut (guarantees autostart without UAC prompt requirement)
$StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$ShortcutPath = Join-Path $StartupDir "$TaskName.lnk"

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.WindowStyle = 7 # Minimized background
    $Shortcut.Description = "AI News Automation Agent Background Autostart Launcher"
    $Shortcut.Save()
    Write-Host "[OK] Registered Windows Startup Shortcut: '$ShortcutPath'" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Could not create Startup shortcut: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " [SUCCESS] WINDOWS AUTOSTART DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Task Name:             $TaskName"
Write-Host " Python Executable:     $PythonExe"
Write-Host " Working Directory:     $ProjectDir"
Write-Host " Autostart Trigger:     Windows User Logon / System Startup"
Write-Host " Background Execution:  Terminal-free execution via start_agent.bat"
Write-Host ""
Write-Host " MANAGE THE AGENT:"
Write-Host " - Start Agent:          .\control_agent.bat START"
Write-Host " - Stop Agent:           .\control_agent.bat STOP"
Write-Host " - Check App Status:     .\control_agent.bat APP-STATUS"
Write-Host " - Uninstall Agent:      .\uninstall_windows_task.bat"
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
