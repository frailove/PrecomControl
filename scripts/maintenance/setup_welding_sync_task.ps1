# 设置焊接记录文件自动同步定时任务
# 功能：创建 Windows 定时任务，每天凌晨 2:00 自动运行同步脚本

param(
    [Parameter(Mandatory=$false)]
    [switch]$Remove,  # 删除现有任务
    
    [Parameter(Mandatory=$false)]
    [string]$Time = "02:00"  # 运行时间（默认凌晨2点）
)

$TaskName = "PrecomControl_WeldingSync"
$ScriptPath = "C:\Projects\PrecomControl\scripts\maintenance\sync_welding_files.ps1"
$TaskDescription = "PrecomControl 焊接记录文件自动同步 - 每天自动同步最新的焊接记录 Excel 文件"

# 检查管理员权限
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "错误: 需要管理员权限来创建定时任务" -ForegroundColor Red
    Write-Host "请以管理员身份运行此脚本" -ForegroundColor Yellow
    exit 1
}

# 检查脚本文件是否存在
if (-not (Test-Path $ScriptPath)) {
    Write-Host "错误: 同步脚本不存在: $ScriptPath" -ForegroundColor Red
    exit 1
}

# 删除现有任务
if ($Remove) {
    Write-Host "正在删除现有定时任务: $TaskName" -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "✓ 定时任务已删除" -ForegroundColor Green
        exit 0
    } catch {
        if ($_.Exception.Message -like "*找不到*") {
            Write-Host "任务不存在，无需删除" -ForegroundColor Yellow
            exit 0
        } else {
            Write-Host "错误: 删除任务失败: $_" -ForegroundColor Red
            exit 1
        }
    }
}

# 检查任务是否已存在
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "警告: 定时任务已存在: $TaskName" -ForegroundColor Yellow
    $response = Read-Host "是否删除并重新创建? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "✓ 已删除现有任务" -ForegroundColor Green
    } else {
        Write-Host "操作已取消" -ForegroundColor Yellow
        exit 0
    }
}

# 创建定时任务
Write-Host "正在创建定时任务..." -ForegroundColor Cyan
Write-Host "  任务名称: $TaskName" -ForegroundColor Gray
Write-Host "  运行时间: 每天 $Time" -ForegroundColor Gray
Write-Host "  脚本路径: $ScriptPath" -ForegroundColor Gray

try {
    # 创建任务动作（执行 PowerShell 脚本）
    # -WindowStyle Hidden: 隐藏窗口，后台运行
    # -NoProfile: 不加载配置文件，加快启动速度
    # -ExecutionPolicy Bypass: 绕过执行策略限制
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    
    # 创建触发器（每天指定时间运行）
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    
    # 创建任务设置
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable:$false `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)
    
    # 创建任务主体（以 SYSTEM 账户运行，或当前用户）
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType S4U `
        -RunLevel Highest
    
    # 注册任务
    Register-ScheduledTask -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $TaskDescription | Out-Null
    
    Write-Host "✓ 定时任务创建成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "任务信息:" -ForegroundColor Cyan
    Write-Host "  名称: $TaskName" -ForegroundColor Gray
    Write-Host "  描述: $TaskDescription" -ForegroundColor Gray
    Write-Host "  运行时间: 每天 $Time" -ForegroundColor Gray
    Write-Host "  状态: $((Get-ScheduledTask -TaskName $TaskName).State)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "管理命令:" -ForegroundColor Yellow
    Write-Host "  查看任务: Get-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "  运行任务: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Gray
    Write-Host "  删除任务: .\setup_welding_sync_task.ps1 -Remove" -ForegroundColor Gray
    Write-Host "  查看日志: Get-Content C:\Projects\PrecomControl\logs\welding_sync.log -Tail 50" -ForegroundColor Gray
    
} catch {
    Write-Host "错误: 创建定时任务失败: $_" -ForegroundColor Red
    exit 1
}
