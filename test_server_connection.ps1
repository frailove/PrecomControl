# Test Server Connection Script
# Run this from the CLIENT machine to test the server

param(
    [string]$ServerIP = "10.78.44.3",
    [int]$Port = 5000
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing Server Connection" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server: $ServerIP:$Port" -ForegroundColor Yellow
Write-Host ""

# Test 1: TCP Connection
Write-Host "1. Testing TCP connection..." -ForegroundColor Yellow
$tcpTest = Test-NetConnection -ComputerName $ServerIP -Port $Port -WarningAction SilentlyContinue
if ($tcpTest.TcpTestSucceeded) {
    Write-Host "   [OK] TCP connection successful!" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] TCP connection failed" -ForegroundColor Red
    Write-Host "   Cannot proceed with HTTP tests" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Test 2: HTTP GET Request (Health Check)
Write-Host "2. Testing HTTP GET request (health check)..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://${ServerIP}:${Port}/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "   [OK] HTTP GET successful!" -ForegroundColor Green
    Write-Host "   Status Code: $($response.StatusCode)" -ForegroundColor Gray
    Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
} catch {
    Write-Host "   [WARNING] HTTP GET failed: $_" -ForegroundColor Yellow
    Write-Host "   This might be normal if /health endpoint doesn't exist" -ForegroundColor Gray
}
Write-Host ""

# Test 3: HTTP GET Request (Root)
Write-Host "3. Testing HTTP GET request (root)..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://${ServerIP}:${Port}/" -TimeoutSec 5 -UseBasicParsing
    Write-Host "   [OK] HTTP GET root successful!" -ForegroundColor Green
    Write-Host "   Status Code: $($response.StatusCode)" -ForegroundColor Gray
} catch {
    Write-Host "   [WARNING] HTTP GET root failed: $_" -ForegroundColor Yellow
}
Write-Host ""

# Test 4: Check if it's a Flask app (check for common Flask headers)
Write-Host "4. Checking server response headers..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://${ServerIP}:${Port}/" -TimeoutSec 5 -UseBasicParsing
    Write-Host "   Response Headers:" -ForegroundColor Cyan
    $response.Headers.GetEnumerator() | ForEach-Object {
        Write-Host "     $($_.Key): $($_.Value)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   [INFO] Could not retrieve headers" -ForegroundColor Gray
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Connection Test Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If TCP connection succeeds but HTTP fails:" -ForegroundColor Yellow
Write-Host "  - Check if Flask app is actually running" -ForegroundColor White
Write-Host "  - Check server logs: logs\app.log" -ForegroundColor White
Write-Host "  - Check if there are any errors in the Flask process" -ForegroundColor White
Write-Host ""

