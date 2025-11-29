# Add Windows Firewall Rule Script
# Allow inbound connections on port 5000

Write-Host "Adding firewall rule..." -ForegroundColor Yellow

try {
    # Check if rule already exists
    $existingRule = Get-NetFirewallRule -DisplayName "Flask App Port 5000" -ErrorAction SilentlyContinue
    
    if ($existingRule) {
        Write-Host "Rule already exists, enabling..." -ForegroundColor Yellow
        Enable-NetFirewallRule -DisplayName "Flask App Port 5000"
        
        # Check if port filter exists
        $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $existingRule | Where-Object { $_.LocalPort -eq 5000 }
        if (-not $portFilter) {
            Write-Host "Warning: Rule exists but port filter may be missing. Removing and recreating..." -ForegroundColor Yellow
            Remove-NetFirewallRule -DisplayName "Flask App Port 5000"
            $existingRule = $null
        } else {
            Write-Host "Rule enabled successfully" -ForegroundColor Green
        }
    }
    
    if (-not $existingRule) {
        # Create new rule
        New-NetFirewallRule `
            -DisplayName "Flask App Port 5000" `
            -Description "Allow Flask app to receive connections on port 5000" `
            -Direction Inbound `
            -LocalPort 5000 `
            -Protocol TCP `
            -Action Allow `
            -Profile Domain,Private,Public
        
        Write-Host "Firewall rule added successfully!" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "Rule details:" -ForegroundColor Cyan
    Get-NetFirewallRule -DisplayName "Flask App Port 5000" | Format-List DisplayName, Enabled, Direction, Action, Profile
    
    Write-Host ""
    Write-Host "Port filter details:" -ForegroundColor Cyan
    $rule = Get-NetFirewallRule -DisplayName "Flask App Port 5000"
    Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule | Format-List LocalPort, Protocol
    
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run this script as Administrator!" -ForegroundColor Yellow
    Write-Host "Right-click PowerShell -> 'Run as Administrator'" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

