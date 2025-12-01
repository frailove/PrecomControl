# Quick check if port 5000 is listening
Write-Host "Checking port 5000 status..." -ForegroundColor Yellow
Write-Host ""

$connections = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue

if ($connections) {
    Write-Host "Port 5000 is active:" -ForegroundColor Green
    $connections | Format-Table LocalAddress, LocalPort, State, OwningProcess -AutoSize
    
    Write-Host ""
    Write-Host "Process details:" -ForegroundColor Cyan
    foreach ($conn in $connections) {
        $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "  PID: $($process.Id) - $($process.ProcessName)" -ForegroundColor Gray
            Write-Host "  Command: $($process.CommandLine)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "Port 5000 is NOT listening!" -ForegroundColor Red
    Write-Host ""
    Write-Host "This means:" -ForegroundColor Yellow
    Write-Host "  - Flask app is not running, OR" -ForegroundColor White
    Write-Host "  - Flask app is not binding to port 5000, OR" -ForegroundColor White
    Write-Host "  - Flask app is only binding to 127.0.0.1 (not accessible from network)" -ForegroundColor White
    Write-Host ""
    Write-Host "To start Flask app:" -ForegroundColor Cyan
    Write-Host "  python wsgi.py" -ForegroundColor White
}

