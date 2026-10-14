@echo off
:: Start the preparer portal locally. Close this window to stop it.
cd /d "%~dp0"
set PYTHON_EXE=%~dp0.venv\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo ERROR: Python virtual environment not found at %PYTHON_EXE%
    pause
    exit /b 1
)

echo Preparer portal: http://127.0.0.1:8800
start "" /B cmd /c "ping -n 3 127.0.0.1 >nul && start http://127.0.0.1:8800"
"%PYTHON_EXE%" run_preparer.py --port 8800
