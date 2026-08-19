@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: AI News Automation Agent - Windows Autostart Uninstaller
:: ============================================================================

set "TASK_NAME=AI News Automation Agent"

echo.
echo ==================================================
echo  AI NEWS AUTOMATION AGENT - UNINSTALLER
echo ==================================================
echo.

:: 1. Stop active daemon process if running
echo Checking for active background daemon processes...
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"

if exist "%PROJECT_DIR%\data\agent.lock" (
    echo Releasing agent lock...
    del /f /q "%PROJECT_DIR%\data\agent.lock" >nul 2>&1
)

:: 2. Remove Windows Task Scheduler Task
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel% eq 0 (
    echo Stopping and deleting Windows Scheduled Task "%TASK_NAME%"...
    schtasks /end /tn "%TASK_NAME%" >nul 2>&1
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
    echo [OK] Removed Windows Scheduled Task.
)

:: 3. Remove Windows Startup Folder Shortcut
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%TASK_NAME%.lnk"
if exist "%SHORTCUT_PATH%" (
    echo Removing Windows Startup folder shortcut...
    del /f /q "%SHORTCUT_PATH%" >nul 2>&1
    echo [OK] Removed Windows Startup shortcut.
)

echo.
echo ==================================================
echo [SUCCESS] Windows Autostart Configuration Removed!
echo ==================================================
echo [NOTE] Your project code, .env, posts.json, and published_news.json remain intact.
echo.
