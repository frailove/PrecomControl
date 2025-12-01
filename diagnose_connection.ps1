# Connection Diagnosis Script
# This script helps diagnose why external connections to Flask app are failing

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Flask App Connection Diagnosis" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check if Flask app is running
Write-Host "1. Checking if Flask app is running..." -ForegroundColor Yellow
$flaskProcess = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*wsgi.py*" -or $_.CommandLine -like "*app.py*"
}
if ($flaskProcess) {
    Write-Host "   [OK] Flask process found (PID: $($flaskProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] Flask process not found. Is the app running?" -ForegroundColor Red
}
Write-Host ""

# 2. Check if port 5000 is listening
Write-Host "2. Checking if port 5000 is listening..." -ForegroundColor Yellow
$listening = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "   [OK] Port 5000 is listening" -ForegroundColor Green
    Write-Host "   Local Address: $($listening.LocalAddress)" -ForegroundColor Gray
    Write-Host "   State: $($listening.State)" -ForegroundColor Gray
} else {
    Write-Host "   [ERROR] Port 5000 is NOT listening!" -ForegroundColor Red
    Write-Host "   This means Flask app is not accepting connections." -ForegroundColor Yellow
}
Write-Host ""

# 3. Check firewall rules
Write-Host "3. Checking firewall rules for port 5000..." -ForegroundColor Yellow
$firewallRules = Get-NetFirewallRule | Where-Object {
    $_.DisplayName -like "*5000*" -or $_.DisplayName -like "*Flask*"
}
if ($firewallRules) {
    foreach ($rule in $firewallRules) {
        $filters = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
        Write-Host "   Rule: $($rule.DisplayName)" -ForegroundColor Cyan
        Write-Host "   Enabled: $($rule.Enabled)" -ForegroundColor Gray
        Write-Host "   Direction: $($rule.Direction)" -ForegroundColor Gray
        Write-Host "   Action: $($rule.Action)" -ForegroundColor Gray
        if ($filters.LocalPort) {
            Write-Host "   Local Port: $($filters.LocalPort)" -ForegroundColor Gray
        }
        Write-Host ""
    }
} else {
    Write-Host "   [WARNING] No firewall rules found for port 5000" -ForegroundColor Yellow
}
Write-Host ""

# 4. Check Windows Firewall profiles
Write-Host "4. Checking Windows Firewall profiles..." -ForegroundColor Yellow
$fwProfiles = Get-NetFirewallProfile
foreach ($profile in $fwProfiles) {
    Write-Host "   Profile: $($profile.Name)" -ForegroundColor Cyan
    Write-Host "   Enabled: $($profile.Enabled)" -ForegroundColor Gray
    Write-Host ""
}
Write-Host ""

# 5. Check for blocking rules
Write-Host "5. Checking for blocking rules on port 5000..." -ForegroundColor Yellow
$blockingRules = Get-NetFirewallRule | Where-Object {
    $_.Action -eq "Block" -and $_.Enabled -eq $true
} | ForEach-Object {
    $filter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $_
    if ($filter.LocalPort -eq 5000 -or $filter.LocalPort -contains 5000) {
        $_
    }
}
if ($blockingRules) {
    Write-Host "   [WARNING] Found blocking rules:" -ForegroundColor Red
    foreach ($rule in $blockingRules) {
        Write-Host "   - $($rule.DisplayName)" -ForegroundColor Yellow
    }
} else {
    Write-Host "   [OK] No blocking rules found for port 5000" -ForegroundColor Green
}
Write-Host ""

# 6. Test local connection
Write-Host "6. Testing local connection to 127.0.0.1:5000..." -ForegroundColor Yellow
try {
    $localTest = Test-NetConnection -ComputerName 127.0.0.1 -Port 5000 -WarningAction SilentlyContinue
    if ($localTest.TcpTestSucceeded) {
        Write-Host "   [OK] Local connection successful" -ForegroundColor Green
    } else {
        Write-Host "   [ERROR] Local connection failed!" -ForegroundColor Red
        Write-Host "   This means Flask app is not running or not listening." -ForegroundColor Yellow
    }
} catch {
    Write-Host "   [ERROR] Local connection test failed: $_" -ForegroundColor Red
}
Write-Host ""

# 7. Get server IP address
Write-Host "7. Server network configuration..." -ForegroundColor Yellow
$ipAddresses = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*"
}
Write-Host "   Server IP addresses:" -ForegroundColor Cyan
foreach ($ip in $ipAddresses) {
    Write-Host "   - $($ip.IPAddress) (Interface: $($ip.InterfaceAlias))" -ForegroundColor Gray
}
Write-Host ""

# 8. Recommendations
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Recommendations:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If port 5000 is not listening:" -ForegroundColor Yellow
Write-Host "  1. Make sure Flask app is running: python wsgi.py" -ForegroundColor White
Write-Host "  2. Check if app is binding to 0.0.0.0:5000 (not just 127.0.0.1)" -ForegroundColor White
Write-Host ""
Write-Host "If firewall rules are correct but connection still fails:" -ForegroundColor Yellow
Write-Host "  1. Check Windows Defender Firewall with Advanced Security" -ForegroundColor White
Write-Host "  2. Check if any antivirus software is blocking connections" -ForegroundColor White
Write-Host "  3. Check network-level firewall (router/switch)" -ForegroundColor White
Write-Host "  4. Verify server IP address matches the one you're connecting to" -ForegroundColor White
Write-Host ""

