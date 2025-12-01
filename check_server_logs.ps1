# Check Server Logs Script
# This script helps diagnose server-side issues by checking Flask logs

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Server Logs Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if logs directory exists
if (Test-Path "logs\app.log") {
    Write-Host "1. Checking recent log entries..." -ForegroundColor Yellow
    Write-Host ""
    
    # Get last 50 lines
    $logContent = Get-Content "logs\app.log" -Tail 50 -ErrorAction SilentlyContinue
    if ($logContent) {
        Write-Host "Last 50 log entries:" -ForegroundColor Cyan
        $logContent | ForEach-Object {
            if ($_ -match "ERROR|CRITICAL") {
                Write-Host $_ -ForegroundColor Red
            } elseif ($_ -match "WARNING") {
                Write-Host $_ -ForegroundColor Yellow
            } elseif ($_ -match "API.*用户.*模块") {
                Write-Host $_ -ForegroundColor Cyan
            } else {
                Write-Host $_ -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "  [WARNING] Log file is empty or cannot be read" -ForegroundColor Yellow
    }
} else {
    Write-Host "1. Log file not found: logs\app.log" -ForegroundColor Yellow
    Write-Host "   Creating logs directory..." -ForegroundColor Gray
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    Write-Host "   [OK] Logs directory created" -ForegroundColor Green
}
Write-Host ""

# Check for specific error patterns
Write-Host "2. Searching for error patterns..." -ForegroundColor Yellow
if (Test-Path "logs\app.log") {
    $errors = Select-String -Path "logs\app.log" -Pattern "ERR_CONNECTION|Connection.*reset|500|Exception|Traceback" -Context 0,2 | Select-Object -Last 10
    if ($errors) {
        Write-Host "   Found error patterns:" -ForegroundColor Red
        $errors | ForEach-Object {
            Write-Host "   $($_.Line)" -ForegroundColor Red
            if ($_.Context.PostContext) {
                $_.Context.PostContext | ForEach-Object {
                    Write-Host "   $_" -ForegroundColor Gray
                }
            }
        }
    } else {
        Write-Host "   [OK] No recent error patterns found" -ForegroundColor Green
    }
}
Write-Host ""

# Check Flask process
Write-Host "3. Checking Flask process..." -ForegroundColor Yellow
$flaskProcess = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*wsgi.py*" -or $_.CommandLine -like "*app.py*"
}
if ($flaskProcess) {
    Write-Host "   [OK] Flask process found (PID: $($flaskProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] Flask process not found" -ForegroundColor Yellow
    Write-Host "   Checking all Python processes..." -ForegroundColor Gray
    Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "   PID: $($_.Id) - $($_.Path)" -ForegroundColor Gray
    }
}
Write-Host ""

# Check port 5000 status
Write-Host "4. Checking port 5000 status..." -ForegroundColor Yellow
$port5000 = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($port5000) {
    Write-Host "   [OK] Port 5000 is listening" -ForegroundColor Green
    Write-Host "   State: $($port5000.State)" -ForegroundColor Gray
    Write-Host "   Local Address: $($port5000.LocalAddress)" -ForegroundColor Gray
} else {
    Write-Host "   [WARNING] Port 5000 is not listening" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Diagnosis Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. If you see errors in the logs, check the error messages above" -ForegroundColor White
Write-Host "2. If Flask process is not running, start it with: python wsgi.py" -ForegroundColor White
Write-Host "3. Monitor logs in real-time: Get-Content logs\app.log -Wait -Tail 20" -ForegroundColor White
Write-Host ""

