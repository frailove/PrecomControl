# 添加 Windows 防火墙规则脚本
# 允许端口 5000 的入站连接

Write-Host "正在添加防火墙规则..." -ForegroundColor Yellow

try {
    # 检查是否已存在规则
    $existingRule = Get-NetFirewallRule -DisplayName "Flask App Port 5000" -ErrorAction SilentlyContinue
    
    if ($existingRule) {
        Write-Host "规则已存在，正在启用..." -ForegroundColor Yellow
        Enable-NetFirewallRule -DisplayName "Flask App Port 5000"
        Write-Host "规则已启用" -ForegroundColor Green
    } else {
        # 创建新规则
        New-NetFirewallRule `
            -DisplayName "Flask App Port 5000" `
            -Description "允许 Flask 应用在端口 5000 上接收连接" `
            -Direction Inbound `
            -LocalPort 5000 `
            -Protocol TCP `
            -Action Allow `
            -Profile Domain,Private,Public
        
        Write-Host "防火墙规则已成功添加！" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "规则详情:" -ForegroundColor Cyan
    Get-NetFirewallRule -DisplayName "Flask App Port 5000" | Format-List DisplayName, Enabled, Direction, Action, Profile
    
} catch {
    Write-Host "错误: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "请以管理员身份运行此脚本！" -ForegroundColor Yellow
    Write-Host "右键点击 PowerShell -> '以管理员身份运行'" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

