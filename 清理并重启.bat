@echo off
chcp 65001 >nul
echo ====================================
echo Clean and Restart Flask Application
echo ====================================
echo.
echo This will:
echo 1. Kill all Python processes
echo 2. Clean up connections
echo 3. Start Flask with HTTPS
echo.
pause

echo.
echo Step 1: Killing all Python processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python3.12.exe >nul 2>&1
echo Done.

echo.
echo Step 2: Waiting for connections to close...
timeout /t 3 /nobreak >nul
echo Done.

echo.
echo Step 3: Starting Flask application...
echo ====================================
python app.py

pause

