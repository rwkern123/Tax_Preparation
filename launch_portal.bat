@echo off
title Tax Client Portal
cd /d "%~dp0"

echo Starting Tax Client Portal...
echo.
echo Portal will be available at: http://127.0.0.1:5050
echo Press Ctrl+C to stop the server.
echo.

start "" "http://127.0.0.1:5050"
python run_portal.py

pause
