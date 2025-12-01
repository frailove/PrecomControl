# Test Remote Connection Script
# Run this from the CLIENT machine (10.78.35.252) to test connection to server

param(
    [string]$ServerIP = "10.78.44.3",
    [int]$Port = 5000
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing Remote Connection" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server: $ServerIP" -ForegroundColor Yellow
Write-Host "Port: $Port" -ForegroundColor Yellow
Write-Host ""

# Test 1: Ping
Write-Host "1. Testing ping..." -ForegroundColor Yellow
$ping = Test-Connection -ComputerName $ServerIP -Count 2 -Quiet
if ($ping) {
    Write-Host "   [OK] Ping successful" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] Ping failed - server may be unreachable" -ForegroundColor Red
    Write-Host "   Check network connectivity first" -ForegroundColor Yellow
    exit
}
Write-Host ""

# Test 2: TCP Connection
Write-Host "2. Testing TCP connection..." -ForegroundColor Yellow
$tcpTest = Test-NetConnection -ComputerName $ServerIP -Port $Port -WarningAction SilentlyContinue
if ($tcpTest.TcpTestSucceeded) {
    Write-Host "   [OK] TCP connection successful!" -ForegroundColor Green
    Write-Host "   Connection is working correctly" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] TCP connection failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Possible causes:" -ForegroundColor Yellow
    Write-Host "   - Firewall blocking connection on server" -ForegroundColor White
    Write-Host "   - Network firewall (router/switch) blocking" -ForegroundColor White
    Write-Host "   - Flask app not running or not listening on 0.0.0.0" -ForegroundColor White
    Write-Host "   - Port 5000 not accessible from network" -ForegroundColor White
}
Write-Host ""

# Test 3: HTTP Request (if TCP succeeds)
if ($tcpTest.TcpTestSucceeded) {
    Write-Host "3. Testing HTTP request..." -ForegroundColor Yellow
    try {
        $response = Invoke-WebRequest -Uri "http://${ServerIP}:${Port}/" -TimeoutSec 5 -UseBasicParsing
        Write-Host "   [OK] HTTP request successful (Status: $($response.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Host "   [WARNING] HTTP request failed: $_" -ForegroundColor Yellow
        Write-Host "   TCP connection works, but HTTP may have issues" -ForegroundColor Yellow
    }
    Write-Host ""
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Diagnosis Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

