@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: AI News Automation Agent - Windows Task & Autostart Installer Wrapper
:: ============================================================================

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\install_windows_task.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installation script encountered an issue. Please review error messages above.
    exit /b %errorlevel%
)
