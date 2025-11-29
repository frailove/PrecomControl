# Cleanup and Create Firewall Rule Script
# Remove all existing "Flask App Port 5000" rules and create a new correct one

Write-Host "Cleaning up existing rules..." -ForegroundColor Yellow

# Get all rules with the same display name
$existingRules = Get-NetFirewallRule -DisplayName "Flask App Port 5000"

if ($existingRules) {
    Write-Host "Found $($existingRules.Count) existing rule(s), removing..." -ForegroundColor Yellow
    foreach ($rule in $existingRules) {
        Remove-NetFirewallRule -Name $rule.Name
        Write-Host "  Removed rule: $($rule.Name)" -ForegroundColor Gray
    }
    Write-Host "All existing rules removed" -ForegroundColor Green
} else {
    Write-Host "No existing rules found" -ForegroundColor Green
}

Write-Host ""
Write-Host "Creating new rule with port 5000..." -ForegroundColor Yellow

# Create new rule with correct parameters
New-NetFirewallRule `
    -DisplayName "Flask App Port 5000" `
    -Description "Allow Flask app to receive connections on port 5000" `
    -Direction Inbound `
    -LocalPort 5000 `
    -Protocol TCP `
    -Action Allow `
    -Profile Domain,Private,Public

Write-Host "New rule created successfully!" -ForegroundColor Green
Write-Host ""

# Verify the rule
Write-Host "Verifying rule..." -ForegroundColor Cyan
$newRule = Get-NetFirewallRule -DisplayName "Flask App Port 5000" | Select-Object -First 1
Write-Host "Rule details:" -ForegroundColor Cyan
$newRule | Format-List DisplayName, Enabled, Direction, Action, Profile

Write-Host ""
Write-Host "Port filter details:" -ForegroundColor Cyan
$portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $newRule
$portFilter | Format-List LocalPort, Protocol

if ($portFilter.LocalPort -eq 5000 -and $portFilter.Protocol -eq "TCP") {
    Write-Host ""
    Write-Host "SUCCESS! Rule is correctly configured with port 5000" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "WARNING: Port filter may not be correct. Trying alternative method..." -ForegroundColor Yellow
    
    # Try using netsh as alternative
    Write-Host "Using netsh to create rule..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName "Flask App Port 5000"
    netsh advfirewall firewall add rule name="Flask App Port 5000" dir=in action=allow protocol=TCP localport=5000
    
    Write-Host "Rule created using netsh. Please verify:" -ForegroundColor Yellow
    netsh advfirewall firewall show rule name="Flask App Port 5000"
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

