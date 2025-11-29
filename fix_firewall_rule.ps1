# Fix Firewall Rule Script
# Remove existing rule and create correct one with port 5000

Write-Host "Fixing firewall rule..." -ForegroundColor Yellow
Write-Host ""

try {
    # Remove existing rule if it exists
    $existingRule = Get-NetFirewallRule -DisplayName "Flask App Port 5000" -ErrorAction SilentlyContinue
    if ($existingRule) {
        Write-Host "Removing existing rule..." -ForegroundColor Yellow
        Remove-NetFirewallRule -DisplayName "Flask App Port 5000"
        Write-Host "Existing rule removed" -ForegroundColor Green
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
    
    Write-Host "Firewall rule created successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Show rule details
    Write-Host "Rule details:" -ForegroundColor Cyan
    $rule = Get-NetFirewallRule -DisplayName "Flask App Port 5000"
    $rule | Format-List DisplayName, Enabled, Direction, Action, Profile
    
    Write-Host ""
    Write-Host "Port filter details:" -ForegroundColor Cyan
    $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
    $portFilter | Format-List LocalPort, Protocol
    
    Write-Host ""
    Write-Host "Rule is ready!" -ForegroundColor Green
    
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run this script as Administrator!" -ForegroundColor Yellow
    Write-Host "Right-click PowerShell -> 'Run as Administrator'" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

