# Start Flask Server Script
# This script ensures proper environment setup and starts the Flask server

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Flask Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check if virtual environment exists
Write-Host "Step 1: Checking virtual environment..." -ForegroundColor Yellow
$venvPath = ".\myenv"
if (Test-Path $venvPath) {
    Write-Host "  [OK] Virtual environment found" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Virtual environment not found!" -ForegroundColor Red
    Write-Host "  Please create it first: python -m venv myenv" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Step 2: Activate virtual environment
Write-Host "Step 2: Activating virtual environment..." -ForegroundColor Yellow
$activateScript = ".\myenv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    & $activateScript
    Write-Host "  [OK] Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] Activation script not found: $activateScript" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 3: Check if port 5000 is already in use
Write-Host "Step 3: Checking port 5000..." -ForegroundColor Yellow
$port5000 = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($port5000) {
    Write-Host "  [WARNING] Port 5000 is already in use!" -ForegroundColor Yellow
    Write-Host "  PID: $($port5000.OwningProcess)" -ForegroundColor Gray
    $process = Get-Process -Id $port5000.OwningProcess -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "  Process: $($process.ProcessName) - $($process.Path)" -ForegroundColor Gray
        Write-Host ""
        $response = Read-Host "  Do you want to stop the existing process? (Y/N)"
        if ($response -eq "Y" -or $response -eq "y") {
            Stop-Process -Id $port5000.OwningProcess -Force
            Write-Host "  [OK] Process stopped" -ForegroundColor Green
            Start-Sleep -Seconds 2
        } else {
            Write-Host "  [INFO] Keeping existing process, exiting..." -ForegroundColor Yellow
            exit 0
        }
    }
} else {
    Write-Host "  [OK] Port 5000 is available" -ForegroundColor Green
}
Write-Host ""

# Step 4: Check database password
Write-Host "Step 4: Checking database password..." -ForegroundColor Yellow
if ($env:DB_PASSWORD) {
    Write-Host "  [OK] DB_PASSWORD is set" -ForegroundColor Green
} else {
    Write-Host "  [WARNING] DB_PASSWORD is not set" -ForegroundColor Yellow
    Write-Host "  Setting default password..." -ForegroundColor Gray
    $env:DB_PASSWORD = 'Gcc$873209'
    Write-Host "  [OK] DB_PASSWORD set" -ForegroundColor Green
}
Write-Host ""

# Step 5: Ensure logs directory exists
Write-Host "Step 5: Ensuring logs directory exists..." -ForegroundColor Yellow
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    Write-Host "  [OK] Logs directory created" -ForegroundColor Green
} else {
    Write-Host "  [OK] Logs directory exists" -ForegroundColor Green
}
Write-Host ""

# Step 6: Start Flask server
Write-Host "Step 6: Starting Flask server..." -ForegroundColor Yellow
Write-Host "  Command: python wsgi.py" -ForegroundColor Gray
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
Write-Host "Monitoring logs in real-time..." -ForegroundColor Cyan
Write-Host ""

# Start Flask server
python wsgi.py

