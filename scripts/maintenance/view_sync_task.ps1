# 查看焊接记录同步定时任务详细信息
# 功能：显示任务的触发时间、运行状态、历史记录等

param(
    [Parameter(Mandatory=$false)]
    [string]$Time  # 修改运行时间（格式：HH:mm，例如 "02:00"）
)

$TaskName = "PrecomControl_WeldingSync"

# 检查任务是否存在
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "错误: 定时任务不存在: $TaskName" -ForegroundColor Red
    Write-Host "请先运行: .\scripts\maintenance\setup_welding_sync_task.ps1" -ForegroundColor Yellow
    exit 1
}

# 修改运行时间
if ($Time) {
    # 验证时间格式
    try {
        $null = [DateTime]::ParseExact($Time, "HH:mm", $null)
    } catch {
        Write-Host "错误: 时间格式不正确，请使用 HH:mm 格式（例如：02:00）" -ForegroundColor Red
        exit 1
    }
    
    # 检查管理员权限
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    
    if (-not $isAdmin) {
        Write-Host "错误: 需要管理员权限来修改定时任务" -ForegroundColor Red
        Write-Host "请以管理员身份运行此脚本" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "正在修改定时任务运行时间..." -ForegroundColor Cyan
    try {
        # 获取现有触发器
        $trigger = $task.Triggers[0]
        
        # 创建新的触发器
        $newTrigger = New-ScheduledTaskTrigger -Daily -At $Time
        
        # 更新任务
        Set-ScheduledTask -TaskName $TaskName -Trigger $newTrigger | Out-Null
        
        Write-Host "✓ 定时任务运行时间已修改为: 每天 $Time" -ForegroundColor Green
        Write-Host ""
    } catch {
        Write-Host "错误: 修改任务失败: $_" -ForegroundColor Red
        exit 1
    }
}

# 显示任务信息
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "定时任务详细信息" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 基本信息
Write-Host "任务名称: $TaskName" -ForegroundColor Yellow
Write-Host "任务状态: $($task.State)" -ForegroundColor $(if ($task.State -eq "Ready") { "Green" } else { "Yellow" })
Write-Host "任务描述: $($task.Description)" -ForegroundColor Gray
Write-Host ""

# 触发器信息
Write-Host "触发设置:" -ForegroundColor Yellow
$trigger = $task.Triggers[0]
if ($trigger) {
    $startBoundary = $trigger.StartBoundary
    if ($startBoundary) {
        $localTime = [DateTime]::Parse($startBoundary).ToLocalTime()
        Write-Host "  运行时间: 每天 $($localTime.ToString('HH:mm'))" -ForegroundColor Green
        Write-Host "  时区: $([TimeZoneInfo]::Local.DisplayName)" -ForegroundColor Gray
    }
    Write-Host "  已启用: $($trigger.Enabled)" -ForegroundColor Gray
    Write-Host "  重复间隔: $($trigger.Repetition.Interval)" -ForegroundColor Gray
}
Write-Host ""

# 运行信息
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "运行信息:" -ForegroundColor Yellow
if ($taskInfo.LastRunTime -and $taskInfo.LastRunTime.Year -gt 2000) {
    $lastRun = $taskInfo.LastRunTime.ToLocalTime()
    Write-Host "  上次运行: $($lastRun.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
    Write-Host "  运行结果: $($taskInfo.LastTaskResult)" -ForegroundColor $(if ($taskInfo.LastTaskResult -eq 0) { "Green" } else { "Red" })
} else {
    Write-Host "  上次运行: 从未运行" -ForegroundColor Gray
}

if ($taskInfo.NextRunTime) {
    $nextRun = $taskInfo.NextRunTime.ToLocalTime()
    Write-Host "  下次运行: $($nextRun.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Green
} else {
    Write-Host "  下次运行: 未计划" -ForegroundColor Yellow
}

Write-Host "  错过运行次数: $($taskInfo.NumberOfMissedRuns)" -ForegroundColor Gray
Write-Host ""

# 动作信息
Write-Host "执行动作:" -ForegroundColor Yellow
$action = $task.Actions[0]
if ($action) {
    Write-Host "  程序: $($action.Execute)" -ForegroundColor Gray
    Write-Host "  参数: $($action.Arguments)" -ForegroundColor Gray
}
Write-Host ""

# 主体信息
Write-Host "运行账户:" -ForegroundColor Yellow
$principal = $task.Principal
if ($principal) {
    Write-Host "  用户: $($principal.UserId)" -ForegroundColor Gray
    Write-Host "  登录类型: $($principal.LogonType)" -ForegroundColor Gray
    Write-Host "  运行级别: $($principal.RunLevel)" -ForegroundColor Gray
}
Write-Host ""

# 管理命令
Write-Host "管理命令:" -ForegroundColor Yellow
Write-Host "  查看任务: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  运行任务: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  停止任务: Stop-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  修改时间: .\scripts\maintenance\view_sync_task.ps1 -Time '02:00'" -ForegroundColor Gray
Write-Host "  查看日志: Get-Content C:\Projects\PrecomControl\logs\welding_sync.log -Tail 50" -ForegroundColor Gray
Write-Host ""

