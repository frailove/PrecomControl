# Check Flask Process Script
# This script identifies which Python process is running Flask

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Flask Process Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check port 5000
Write-Host "1. Checking port 5000 connections..." -ForegroundColor Yellow
$port5000 = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue
if ($port5000) {
    Write-Host "  Found connection(s) on port 5000:" -ForegroundColor Green
    $port5000 | ForEach-Object {
        $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "    PID: $($_.OwningProcess)" -ForegroundColor Cyan
            Write-Host "    State: $($_.State)" -ForegroundColor Gray
            Write-Host "    Local Address: $($_.LocalAddress):$($_.LocalPort)" -ForegroundColor Gray
            Write-Host "    Process: $($process.ProcessName)" -ForegroundColor Gray
            Write-Host "    Path: $($process.Path)" -ForegroundColor Gray
            
            # Try to get command line (requires admin rights)
            try {
                $wmi = Get-WmiObject Win32_Process -Filter "ProcessId = $($_.OwningProcess)" -ErrorAction SilentlyContinue
                if ($wmi) {
                    Write-Host "    Command: $($wmi.CommandLine)" -ForegroundColor Gray
                    if ($wmi.CommandLine -like "*wsgi.py*" -or $wmi.CommandLine -like "*app.py*") {
                        Write-Host "    [OK] This is the Flask process!" -ForegroundColor Green
                    }
                }
            } catch {
                Write-Host "    [INFO] Cannot get command line (requires admin rights)" -ForegroundColor Yellow
            }
            Write-Host ""
        }
    }
} else {
    Write-Host "  [WARNING] No connections found on port 5000" -ForegroundColor Yellow
    Write-Host "  Flask server may not be running" -ForegroundColor Yellow
}
Write-Host ""

# Check all Python processes
Write-Host "2. Checking all Python processes..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    Write-Host "  Found $($pythonProcesses.Count) Python process(es):" -ForegroundColor Green
    $pythonProcesses | ForEach-Object {
        Write-Host "    PID: $($_.Id)" -ForegroundColor Cyan
        Write-Host "    Path: $($_.Path)" -ForegroundColor Gray
        
        # Try to get command line
        try {
            $wmi = Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue
            if ($wmi) {
                Write-Host "    Command: $($wmi.CommandLine)" -ForegroundColor Gray
                if ($wmi.CommandLine -like "*wsgi.py*" -or $wmi.CommandLine -like "*app.py*") {
                    Write-Host "    [OK] This is the Flask process!" -ForegroundColor Green
                }
            }
        } catch {
            Write-Host "    [INFO] Cannot get command line" -ForegroundColor Yellow
        }
        Write-Host ""
    }
} else {
    Write-Host "  [INFO] No Python processes found" -ForegroundColor Yellow
}
Write-Host ""

# Check if logs directory exists and has files
Write-Host "3. Checking logs..." -ForegroundColor Yellow
if (Test-Path "logs\app.log") {
    $logFile = Get-Item "logs\app.log"
    Write-Host "  [OK] Log file exists: logs\app.log" -ForegroundColor Green
    Write-Host "    Size: $([math]::Round($logFile.Length / 1KB, 2)) KB" -ForegroundColor Gray
    Write-Host "    Last Modified: $($logFile.LastWriteTime)" -ForegroundColor Gray
    
    # Show last 10 lines
    Write-Host ""
    Write-Host "  Last 10 log entries:" -ForegroundColor Cyan
    Get-Content "logs\app.log" -Tail 10 | ForEach-Object {
        if ($_ -match "ERROR|CRITICAL") {
            Write-Host "    $_" -ForegroundColor Red
        } elseif ($_ -match "WARNING") {
            Write-Host "    $_" -ForegroundColor Yellow
        } else {
            Write-Host "    $_" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "  [WARNING] Log file not found: logs\app.log" -ForegroundColor Yellow
    Write-Host "  This may indicate the Flask app hasn't started yet or logging isn't configured" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Diagnosis Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. If Flask is not running, start it with:" -ForegroundColor White
Write-Host "   powershell -ExecutionPolicy Bypass -File .\start_flask_server.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Monitor logs in real-time:" -ForegroundColor White
Write-Host "   Get-Content logs\app.log -Wait -Tail 20" -ForegroundColor Gray
Write-Host ""

