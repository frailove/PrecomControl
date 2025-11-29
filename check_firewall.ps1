# Windows 防火墙检查脚本
# 用于检查 Flask 应用（端口 5000）的防火墙规则

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Windows 防火墙规则检查" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查入站规则
Write-Host "检查端口 5000 的入站规则..." -ForegroundColor Yellow
$inboundRules = Get-NetFirewallRule | Where-Object {
    $_.DisplayName -like "*5000*" -or 
    $_.DisplayName -like "*Flask*" -or 
    $_.DisplayName -like "*Precom*"
}

if ($inboundRules) {
    Write-Host "找到相关入站规则:" -ForegroundColor Green
    $inboundRules | Format-Table DisplayName, Enabled, Direction, Action -AutoSize
} else {
    Write-Host "未找到端口 5000 的入站规则" -ForegroundColor Red
}

Write-Host ""

# 检查端口过滤器
Write-Host "检查端口 5000 的端口过滤器..." -ForegroundColor Yellow
$portFilters = Get-NetFirewallPortFilter | Where-Object {
    $_.LocalPort -eq 5000
}

if ($portFilters) {
    Write-Host "找到端口 5000 的过滤器:" -ForegroundColor Green
    $portFilters | ForEach-Object {
        $rule = Get-NetFirewallRule -AssociatedNetFirewallPortFilter $_
        Write-Host "  规则: $($rule.DisplayName), 状态: $($rule.Enabled), 操作: $($rule.Action)"
    }
} else {
    Write-Host "未找到端口 5000 的端口过滤器" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "建议操作" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "如果没有找到端口 5000 的防火墙规则，可以运行以下命令添加:" -ForegroundColor Yellow
Write-Host ""
Write-Host "New-NetFirewallRule -DisplayName 'Flask App Port 5000' -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow" -ForegroundColor White
Write-Host ""
Write-Host "或者使用图形界面:" -ForegroundColor Yellow
Write-Host "1. 打开 'Windows Defender 防火墙' -> '高级设置'" -ForegroundColor White
Write-Host "2. 选择 '入站规则' -> '新建规则'" -ForegroundColor White
Write-Host "3. 选择 '端口' -> 'TCP' -> '特定本地端口: 5000'" -ForegroundColor White
Write-Host "4. 选择 '允许连接'" -ForegroundColor White
Write-Host "5. 应用到所有配置文件" -ForegroundColor White
Write-Host "6. 命名为 'Flask App Port 5000'" -ForegroundColor White
Write-Host ""

