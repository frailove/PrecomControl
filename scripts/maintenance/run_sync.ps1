# 快速运行焊接记录文件同步（后台模式）
# 用于手动触发同步，不显示窗口

$scriptPath = Join-Path $PSScriptRoot "sync_welding_files.ps1"

Write-Host "正在后台运行焊接记录文件同步..." -ForegroundColor Cyan
Write-Host "日志文件: C:\Projects\PrecomControl\logs\welding_sync.log" -ForegroundColor Gray
Write-Host ""

# 后台运行，不显示窗口
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -ShowVerbose" -WindowStyle Hidden

Write-Host "✓ 同步任务已在后台启动" -ForegroundColor Green
Write-Host ""
Write-Host "查看日志命令:" -ForegroundColor Yellow
Write-Host "  Get-Content C:\Projects\PrecomControl\logs\welding_sync.log -Tail 50" -ForegroundColor Gray

