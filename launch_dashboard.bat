@echo off
:: Tax Preparer Dashboard Launcher
:: Double-click this file to start the dashboard and open it in your browser.
:: Close this window to stop the server.

cd /d "%~dp0"

set PYTHON="%~dp0.venv\Scripts\python.exe"

if not exist %PYTHON% (
    echo ERROR: Python virtual environment not found.
    echo Expected: %~dp0.venv\Scripts\python.exe
    echo.
    echo Please contact your administrator.
    pause
    exit /b 1
)

echo ============================================================
echo   Tax Preparer Dashboard
echo   http://127.0.0.1:8800
echo   Close this window to stop the server.
echo ============================================================
echo.

:: Open the browser after a short delay (runs in background)
start "" /B cmd /c "ping -n 3 127.0.0.1 >nul && start http://127.0.0.1:8800"

:: Start the server — this line blocks until the window is closed
%PYTHON% run_preparer.py --port 8800
