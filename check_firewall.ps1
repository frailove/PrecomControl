# Windows Firewall Check Script
# Check firewall rules for Flask app (port 5000)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Windows Firewall Rules Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check inbound rules
Write-Host "Checking inbound rules for port 5000..." -ForegroundColor Yellow
$inboundRules = Get-NetFirewallRule | Where-Object {
    $_.DisplayName -like "*5000*" -or 
    $_.DisplayName -like "*Flask*" -or 
    $_.DisplayName -like "*Precom*"
}

if ($inboundRules) {
    Write-Host "Found related inbound rules:" -ForegroundColor Green
    $inboundRules | Format-Table DisplayName, Enabled, Direction, Action -AutoSize
} else {
    Write-Host "No inbound rules found for port 5000" -ForegroundColor Red
}

Write-Host ""

# Check port filters
Write-Host "Checking port filters for port 5000..." -ForegroundColor Yellow
$portFilters = Get-NetFirewallPortFilter | Where-Object {
    $_.LocalPort -eq 5000
}

if ($portFilters) {
    Write-Host "Found port filters for port 5000:" -ForegroundColor Green
    $portFilters | ForEach-Object {
        $rule = Get-NetFirewallRule -AssociatedNetFirewallPortFilter $_
        Write-Host "  Rule: $($rule.DisplayName), Status: $($rule.Enabled), Action: $($rule.Action)"
    }
} else {
    Write-Host "No port filters found for port 5000" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Recommended Actions" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "If no firewall rules found for port 5000, run the following command:" -ForegroundColor Yellow
Write-Host ""
Write-Host "New-NetFirewallRule -DisplayName 'Flask App Port 5000' -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -Profile Domain,Private,Public" -ForegroundColor White
Write-Host ""
Write-Host "Or use GUI:" -ForegroundColor Yellow
Write-Host "1. Open 'Windows Defender Firewall' -> 'Advanced settings'" -ForegroundColor White
Write-Host "2. Select 'Inbound Rules' -> 'New Rule...'" -ForegroundColor White
Write-Host "3. Select 'Port' -> 'TCP' -> 'Specific local ports: 5000'" -ForegroundColor White
Write-Host "4. Select 'Allow the connection'" -ForegroundColor White
Write-Host "5. Apply to all profiles" -ForegroundColor White
Write-Host "6. Name it 'Flask App Port 5000'" -ForegroundColor White
Write-Host ""

