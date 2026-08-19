@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: AI News Automation Agent - Control Script
:: ============================================================================

set "TASK_NAME=AI News Automation Agent"
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

set "PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
)

set "ACTION=%~1"
if "%ACTION%"=="" (
    echo Usage: control_agent.bat [START ^| STOP ^| RESTART ^| STATUS ^| APP-STATUS]
    exit /b 1
)

if /i "%ACTION%"=="START" (
    echo Starting Windows Task: "%TASK_NAME%"...
    schtasks /run /tn "%TASK_NAME%"
    exit /b 0
)

if /i "%ACTION%"=="STOP" (
    echo Stopping Windows Task: "%TASK_NAME%"...
    schtasks /end /tn "%TASK_NAME%"
    exit /b 0
)

if /i "%ACTION%"=="RESTART" (
    echo Restarting Windows Task: "%TASK_NAME%"...
    schtasks /end /tn "%TASK_NAME%" >nul 2>&1
    timeout /t 2 /nobreak >nul
    schtasks /run /tn "%TASK_NAME%"
    exit /b 0
)

if /i "%ACTION%"=="STATUS" (
    echo Checking Windows Task Scheduler Status...
    schtasks /query /tn "%TASK_NAME%" /v /fo LIST
    exit /b 0
)

if /i "%ACTION%"=="APP-STATUS" (
    if exist "%PYTHON_EXE%" (
        "%PYTHON_EXE%" "%PROJECT_DIR%\main.py" --status
    ) else (
        python "%PROJECT_DIR%\main.py" --status
    )
    exit /b 0
)

echo Unknown action: %ACTION%
echo Usage: control_agent.bat [START ^| STOP ^| RESTART ^| STATUS ^| APP-STATUS]
