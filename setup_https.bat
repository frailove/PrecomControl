@echo off
chcp 65001 >nul
echo ====================================
echo HTTPS Setup Wizard
echo ====================================
echo.
echo This script will:
echo 1. Install cryptography library
echo 2. Generate SSL self-signed certificate
echo 3. Configure Flask to use HTTPS
echo.
pause

echo.
echo [1/2] Installing cryptography...
echo ====================================
myenv\Scripts\pip.exe install cryptography

echo.
echo [2/2] Generating SSL certificate...
echo ====================================
myenv\Scripts\python.exe generate_ssl_cert.py

echo.
echo ====================================
echo HTTPS Setup Completed!
echo ====================================
echo.
echo Next steps:
echo   1. Run: python app.py
echo   2. Visit: https://10.78.80.29:5000
echo   3. Click "Continue" in browser warning
echo.
pause

