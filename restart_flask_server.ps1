# Restart Flask Server Script
# This script safely stops existing Flask processes and restarts the server

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Restarting Flask Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Find and stop existing Flask processes
Write-Host "Step 1: Stopping existing Flask processes..." -ForegroundColor Yellow
$flaskProcesses = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    try {
        $wmi = Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue
        if ($wmi -and ($wmi.CommandLine -like "*wsgi.py*" -or $wmi.CommandLine -like "*app.py*")) {
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

if ($flaskProcesses) {
    Write-Host "  Found $($flaskProcesses.Count) Flask process(es):" -ForegroundColor Cyan
    $flaskProcesses | ForEach-Object {
        Write-Host "    Stopping PID: $($_.Id)" -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  [OK] All Flask processes stopped" -ForegroundColor Green
    Start-Sleep -Seconds 2
} else {
    Write-Host "  [OK] No Flask processes found" -ForegroundColor Green
}
Write-Host ""

# Step 2: Check if port 5000 is free
Write-Host "Step 2: Checking port 5000..." -ForegroundColor Yellow
$port5000 = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($port5000) {
    Write-Host "  [WARNING] Port 5000 is still in use, waiting..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    $port5000 = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
    if ($port5000) {
        Write-Host "  [ERROR] Port 5000 is still in use after waiting" -ForegroundColor Red
        Write-Host "  Please manually stop the process using port 5000" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "  [OK] Port 5000 is free" -ForegroundColor Green
Write-Host ""

# Step 3: Check virtual environment
Write-Host "Step 3: Checking virtual environment..." -ForegroundColor Yellow
$venvPath = ".\myenv"
if (Test-Path $venvPath) {
    Write-Host "  [OK] Virtual environment found" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Virtual environment not found!" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 4: Activate virtual environment
Write-Host "Step 4: Activating virtual environment..." -ForegroundColor Yellow
$activateScript = ".\myenv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    & $activateScript
    Write-Host "  [OK] Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Activation script not found" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 5: Set database password
Write-Host "Step 5: Setting database password..." -ForegroundColor Yellow
$env:DB_PASSWORD = 'Gcc$873209'
Write-Host "  [OK] DB_PASSWORD set" -ForegroundColor Green
Write-Host ""

# Step 6: Ensure logs directory exists
Write-Host "Step 6: Ensuring logs directory exists..." -ForegroundColor Yellow
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    Write-Host "  [OK] Logs directory created" -ForegroundColor Green
} else {
    Write-Host "  [OK] Logs directory exists" -ForegroundColor Green
}
Write-Host ""

# Step 7: Start Flask server
Write-Host "Step 7: Starting Flask server..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Flask Server Starting..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server will be available at:" -ForegroundColor Yellow
Write-Host "  - http://127.0.0.1:5000" -ForegroundColor White
Write-Host "  - http://10.78.44.3:5000" -ForegroundColor White
Write-Host ""
Write-Host "Press CTRL+C to stop the server" -ForegroundColor Gray
Write-Host ""

# Start Flask server in the current session
python wsgi.py

