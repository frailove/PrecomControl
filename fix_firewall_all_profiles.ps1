# Fix Firewall Rule for All Profiles
# This script ensures the firewall rule applies to all network profiles

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fixing Firewall Rule for All Profiles" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Remove existing rules
Write-Host "Step 1: Removing existing rules..." -ForegroundColor Yellow
$existingRules = Get-NetFirewallRule -DisplayName "Flask App Port 5000" -ErrorAction SilentlyContinue
if ($existingRules) {
    foreach ($rule in $existingRules) {
        Remove-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue
        Write-Host "  Removed: $($rule.Name)" -ForegroundColor Gray
    }
    Write-Host "  [OK] Existing rules removed" -ForegroundColor Green
} else {
    Write-Host "  [OK] No existing rules to remove" -ForegroundColor Green
}
Write-Host ""

# Step 2: Create rule using netsh (more reliable for port specification)
Write-Host "Step 2: Creating new rule using netsh..." -ForegroundColor Yellow
netsh advfirewall firewall delete rule name="Flask App Port 5000" > $null 2>&1
netsh advfirewall firewall add rule name="Flask App Port 5000" dir=in action=allow protocol=TCP localport=5000 profile=any
Write-Host "  [OK] Rule created using netsh" -ForegroundColor Green
Write-Host ""

# Step 3: Verify the rule
Write-Host "Step 3: Verifying rule configuration..." -ForegroundColor Yellow
$rule = Get-NetFirewallRule -DisplayName "Flask App Port 5000" -ErrorAction SilentlyContinue
if ($rule) {
    Write-Host "  Rule found:" -ForegroundColor Cyan
    Write-Host "    Name: $($rule.Name)" -ForegroundColor Gray
    Write-Host "    DisplayName: $($rule.DisplayName)" -ForegroundColor Gray
    Write-Host "    Enabled: $($rule.Enabled)" -ForegroundColor Gray
    Write-Host "    Direction: $($rule.Direction)" -ForegroundColor Gray
    Write-Host "    Action: $($rule.Action)" -ForegroundColor Gray
    Write-Host "    Profile: $($rule.Profile)" -ForegroundColor Gray
    
    $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
    Write-Host "    Local Port: $($portFilter.LocalPort)" -ForegroundColor Gray
    Write-Host "    Protocol: $($portFilter.Protocol)" -ForegroundColor Gray
    
    if ($portFilter.LocalPort -eq 5000 -and $rule.Enabled -eq $true) {
        Write-Host "  [OK] Rule is correctly configured!" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] Rule configuration may be incorrect" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [ERROR] Rule not found!" -ForegroundColor Red
}
Write-Host ""

# Step 4: Check firewall profiles
Write-Host "Step 4: Checking firewall profiles..." -ForegroundColor Yellow
$profiles = Get-NetFirewallProfile
foreach ($fwProfile in $profiles) {
    $status = if ($fwProfile.Enabled) { "Enabled" } else { "Disabled" }
    $color = if ($fwProfile.Enabled) { "Green" } else { "Yellow" }
    Write-Host "  $($fwProfile.Name): $status" -ForegroundColor $color
}
Write-Host ""

# Step 5: Test local connection to external IP
Write-Host "Step 5: Testing connection to server's external IP..." -ForegroundColor Yellow
$serverIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*"
}).IPAddress | Select-Object -First 1

if ($serverIP) {
    Write-Host "  Server IP: $serverIP" -ForegroundColor Cyan
    Write-Host "  Testing connection to $serverIP:5000..." -ForegroundColor Gray
    $test = Test-NetConnection -ComputerName $serverIP -Port 5000 -WarningAction SilentlyContinue
    if ($test.TcpTestSucceeded) {
        Write-Host "  [OK] Connection to external IP successful!" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] Connection to external IP failed" -ForegroundColor Yellow
        Write-Host "  This might indicate a network-level firewall issue" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [WARNING] Could not determine server IP" -ForegroundColor Yellow
}
Write-Host ""

# Step 6: Show netsh output for verification
Write-Host "Step 6: Showing netsh rule details..." -ForegroundColor Yellow
netsh advfirewall firewall show rule name="Flask App Port 5000"
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. If connection still fails from remote machine:" -ForegroundColor Yellow
Write-Host "   - Check if there's a network firewall (router/switch)" -ForegroundColor White
Write-Host "   - Check Windows Defender Firewall with Advanced Security" -ForegroundColor White
Write-Host "   - Verify the server IP address is correct" -ForegroundColor White
Write-Host ""
Write-Host "2. Test from remote machine:" -ForegroundColor Yellow
Write-Host "   Test-NetConnection -ComputerName 10.78.44.3 -Port 5000" -ForegroundColor White
Write-Host ""
Write-Host "3. If still failing, check Windows Defender Firewall logs:" -ForegroundColor Yellow
Write-Host "   Get-WinEvent -LogName 'Microsoft-Windows-Windows Firewall With Advanced Security/Firewall' | Select-Object -First 10" -ForegroundColor White
Write-Host ""

