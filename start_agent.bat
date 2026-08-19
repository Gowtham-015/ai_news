@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: AI News Automation Agent - Windows Autostart Launcher
:: ============================================================================

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

set "PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment Python not found in %PROJECT_DIR%\venv or %PROJECT_DIR%\.venv
    exit /b 1
)

"%PYTHON_EXE%" "%PROJECT_DIR%\main.py" --daemon
