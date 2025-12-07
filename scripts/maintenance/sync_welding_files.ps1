# PrecomControl 焊接记录文件自动同步脚本
# 功能：从源文件夹同步最新的焊接记录 Excel 文件到项目目录
# 支持：定时任务自动运行、手动后台运行

param(
    [Parameter(Mandatory=$false)]
    [switch]$ShowVerbose,  # 详细输出模式
    
    [Parameter(Mandatory=$false)]
    [switch]$Test,      # 测试模式（不实际复制文件）
    
    [Parameter(Mandatory=$false)]
    [switch]$AutoImport  # 同步后自动导入数据到数据库（需要虚拟环境）
)

# 配置参数
$SourceBasePath = "Z:\16-无损检测资料 NDT （заявка и заключение НК и РК）\12 焊接记录查询 журнал сварочных работ"
$TargetPath = "C:\Projects\PrecomControl\nordinfo"
$LogPath = "C:\Projects\PrecomControl\logs\welding_sync.log"
$FilePattern = "WeldingDB_*.xlsx"

# 确保日志目录存在
$logDir = Split-Path -Parent $LogPath
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# 日志函数
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    # 写入日志文件
    Add-Content -Path $LogPath -Value $logMessage -Encoding UTF8
    
    # 根据级别输出到控制台
    switch ($Level) {
        "ERROR" { Write-Host $logMessage -ForegroundColor Red }
        "WARNING" { Write-Host $logMessage -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logMessage -ForegroundColor Green }
        default {
            if ($ShowVerbose) {
                Write-Host $logMessage -ForegroundColor Cyan
            }
        }
    }
}

# 从加密文件读取数据库密码
function Get-DbPasswordFromFile {
    $scriptDir = Split-Path -Parent $MyInvocation.ScriptName
    $projectRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
    $passwordFile = Join-Path $projectRoot "config\db_password.encrypted"
    
    if (-not (Test-Path $passwordFile)) {
        return $null
    }
    
    try {
        # 读取加密的 Base64 字符串
        $encrypted = Get-Content $passwordFile -Raw
        
        # 转换为字节数组
        $encryptedBytes = [Convert]::FromBase64String($encrypted)
        
        # 使用 DPAPI 解密（CurrentUser 范围）
        $decryptedBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $encryptedBytes,
            $null,
            [System.Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        
        # 转换为字符串
        $password = [System.Text.Encoding]::UTF8.GetString($decryptedBytes)
        return $password
    } catch {
        Write-Log "警告: 无法从加密文件读取密码: $_" "WARNING"
        return $null
    }
}

# 主函数
function Sync-WeldingFiles {
    Write-Log "========================================" "INFO"
    Write-Log "开始同步焊接记录文件" "INFO"
    Write-Log "========================================" "INFO"
    
    # 1. 检查源路径是否存在
    if (-not (Test-Path $SourceBasePath)) {
        Write-Log "错误: 源路径不存在: $SourceBasePath" "ERROR"
        return $false
    }
    Write-Log "✓ 源路径检查通过: $SourceBasePath" "SUCCESS"
    
    # 2. 检查目标路径是否存在
    if (-not (Test-Path $TargetPath)) {
        Write-Log "警告: 目标路径不存在，正在创建: $TargetPath" "WARNING"
        try {
            New-Item -ItemType Directory -Path $TargetPath -Force | Out-Null
            Write-Log "✓ 目标路径创建成功" "SUCCESS"
        } catch {
            Write-Log "错误: 无法创建目标路径: $_" "ERROR"
            return $false
        }
    }
    Write-Log "✓ 目标路径检查通过: $TargetPath" "SUCCESS"
    
    # 3. 查找源路径下最新的文件夹
    Write-Log "正在查找最新创建的文件夹..." "INFO"
    try {
        $folders = Get-ChildItem -Path $SourceBasePath -Directory -ErrorAction Stop | 
            Sort-Object CreationTime -Descending
        
        if ($folders.Count -eq 0) {
            Write-Log "错误: 源路径下没有找到任何文件夹" "ERROR"
            return $false
        }
        
        $latestFolder = $folders[0]
        Write-Log "✓ 找到最新文件夹: $($latestFolder.Name)" "SUCCESS"
        Write-Log "  创建时间: $($latestFolder.CreationTime)" "INFO"
        Write-Log "  完整路径: $($latestFolder.FullName)" "INFO"
    } catch {
        Write-Log "错误: 无法访问源路径: $_" "ERROR"
        return $false
    }
    
    # 4. 在最新文件夹中查找所有 xlsx 文件
    Write-Log "正在查找 Excel 文件..." "INFO"
    try {
        $sourceFiles = Get-ChildItem -Path $latestFolder.FullName -Filter "*.xlsx" -File -ErrorAction Stop
        
        if ($sourceFiles.Count -eq 0) {
            Write-Log "警告: 最新文件夹中没有找到 Excel 文件" "WARNING"
            return $false
        }
        
        Write-Log "✓ 找到 $($sourceFiles.Count) 个 Excel 文件" "SUCCESS"
        foreach ($file in $sourceFiles) {
            $fileSizeKB = [math]::Round($file.Length / 1024, 2)
            $sizeText = "$fileSizeKB KB"
            Write-Log "  - $($file.Name) ($sizeText)" "INFO"
        }
    } catch {
        Write-Log "错误: 无法访问文件夹内容: $_" "ERROR"
        return $false
    }
    
    # 5. 删除目标路径中的旧文件（WeldingDB_*.xlsx）
    Write-Log "正在删除旧文件..." "INFO"
    try {
        $targetFiles = Get-ChildItem -Path $TargetPath -Filter $FilePattern -File -ErrorAction SilentlyContinue
        
        if ($targetFiles.Count -gt 0) {
            Write-Log "  找到 $($targetFiles.Count) 个旧文件需要删除" "INFO"
            foreach ($file in $targetFiles) {
                if (-not $Test) {
                    Remove-Item -Path $file.FullName -Force -ErrorAction Stop
                    Write-Log "  ✓ 已删除: $($file.Name)" "INFO"
                } else {
                    Write-Log "  [测试模式] 将删除: $($file.Name)" "INFO"
                }
            }
            Write-Log "✓ 旧文件处理完成" "SUCCESS"
        } else {
            Write-Log "  未找到旧文件，将直接复制新文件" "INFO"
        }
    } catch {
        Write-Log "错误: 删除旧文件失败: $_" "ERROR"
        return $false
    }
    
    # 6. 复制新文件到目标路径并重命名
    Write-Log "正在复制新文件（将重命名为 WeldingDB_*.xlsx）..." "INFO"
    $successCount = 0
    $failCount = 0
    $fileIndex = 1
    
    foreach ($sourceFile in $sourceFiles) {
        # 生成目标文件名：WeldingDB_1.xlsx, WeldingDB_2.xlsx, ...
        $targetFileName = "WeldingDB_$fileIndex.xlsx"
        $targetFile = Join-Path $TargetPath $targetFileName
        
        if ($Test) {
            Write-Log "  [测试模式] 将复制: $($sourceFile.Name) -> $targetFileName" "INFO"
            $successCount++
            $fileIndex++
        } else {
            try {
                Copy-Item -Path $sourceFile.FullName -Destination $targetFile -Force -ErrorAction Stop
                $fileSizeKB = [math]::Round($sourceFile.Length / 1024, 2)
                $sizeText = "$fileSizeKB KB"
                Write-Log "  ✓ 已复制并重命名: $($sourceFile.Name) -> $targetFileName ($sizeText)" "SUCCESS"
                $successCount++
                $fileIndex++
            } catch {
                Write-Log "  ✗ 复制失败: $($sourceFile.Name) - $_" "ERROR"
                $failCount++
            }
        }
    }
    
    # 9. 总结文件同步结果
    Write-Log "========================================" "INFO"
    if ($Test) {
        Write-Log "测试模式完成" "INFO"
        Write-Log "  将复制 $successCount 个文件" "INFO"
    } else {
        if ($failCount -eq 0) {
            Write-Log "✓ 文件同步完成！成功复制 $successCount 个文件" "SUCCESS"
        } else {
            Write-Log "同步部分完成: 成功 $successCount 个，失败 $failCount 个" "WARNING"
        }
    }
    Write-Log "========================================" "INFO"
    
    # 10. 可选：自动运行数据同步流水线（备份、导入、同步、聚合、清理）
    if ($AutoImport -and $failCount -eq 0 -and $successCount -gt 0) {
        Write-Log "" "INFO"
        Write-Log "========================================" "INFO"
        Write-Log "开始执行数据同步流水线" "INFO"
        Write-Log "  步骤：备份 → 导入 → 同步 → 聚合 → 清理" "INFO"
        Write-Log "========================================" "INFO"
        try {
            $projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
            $venvPath = Join-Path $projectRoot "myenv"
            $pythonExe = Join-Path $venvPath "Scripts\python.exe"
            $importScript = Join-Path $projectRoot "maintenance\data_sync_pipeline.py"
            
            if (-not (Test-Path $pythonExe)) {
                Write-Log "警告: 未找到虚拟环境，跳过数据导入" "WARNING"
                Write-Log "  虚拟环境路径: $venvPath" "WARNING"
                Write-Log "  请手动运行数据导入脚本" "WARNING"
                return ($failCount -eq 0)
            }
            
            Write-Log "  使用虚拟环境: $venvPath" "INFO"
            
            # 检查数据库密码：优先从环境变量，其次从加密文件，最后提示输入
            if (-not $env:DB_PASSWORD) {
                # 尝试从加密文件读取
                $encryptedPassword = Get-DbPasswordFromFile
                if ($encryptedPassword) {
                    $env:DB_PASSWORD = $encryptedPassword
                    Write-Log "✓ 已从加密文件读取数据库密码" "SUCCESS"
                } else {
                    # 如果加密文件不存在，提示用户输入
                    Write-Log "  需要数据库密码以进行数据导入" "INFO"
                    Write-Host ""
                    Write-Host "提示: 可以运行以下命令预先设置密码（避免每次输入）:" -ForegroundColor Yellow
                    Write-Host "  .\scripts\maintenance\set_db_password.ps1" -ForegroundColor Gray
                    Write-Host ""
                    Write-Host "请输入MySQL数据库密码:" -ForegroundColor Cyan
                    Write-Host "(密码输入时不会显示，输入完成后按回车)" -ForegroundColor Gray
                    
                    # 使用 SecureString 读取密码（不在屏幕上显示）
                    Write-Host "数据库密码: " -NoNewline -ForegroundColor Cyan
                    $securePassword = Read-Host -AsSecureString
                    
                    # 将 SecureString 转换为普通字符串（用于环境变量）
                    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
                    $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
                    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
                    
                    # 设置环境变量（仅当前进程有效）
                    $env:DB_PASSWORD = $plainPassword
                    Write-Log "✓ 数据库密码已设置" "SUCCESS"
                    Write-Host ""
                }
            } else {
                Write-Log "  数据库密码环境变量已设置" "INFO"
            }
            
            # 调用 data_sync_pipeline.py 执行完整的数据同步流水线
            # 该脚本会执行：备份 → 导入 WeldingList → 同步主数据 → 刷新聚合表 → 数据清理
            Write-Log "  正在调用 data_sync_pipeline.py..." "INFO"
            Write-Log "  数据源路径: $TargetPath" "INFO"
            Write-Log "  触发来源: FILE_SYNC_AUTO" "INFO"
            Write-Host ""
            Write-Host ("=" * 70) -ForegroundColor Cyan
            Write-Host "数据同步流水线启动（这可能需要几分钟）" -ForegroundColor Yellow
            Write-Host "  步骤：[1/5] 备份 → [2/5] 导入 → [3/5] 同步 → [4/5] 聚合 → [5/5] 清理" -ForegroundColor Gray
            Write-Host ("=" * 70) -ForegroundColor Cyan
            Write-Host ""
            
            # 构建 Python 命令参数
            # --excel: 传递 nordinfo 目录路径，Python 脚本会自动查找所有 WeldingDB_*.xlsx 文件
            # --trigger: 标记为文件同步自动触发
            # 使用 -u 参数禁用 Python 输出缓冲，确保实时显示输出
            $pythonArgs = @(
                "-u",  # 禁用输出缓冲（unbuffered mode）
                $importScript,
                "--excel", $TargetPath,
                "--trigger", "FILE_SYNC_AUTO"
            )
            
            # 实时显示输出
            # 使用 Start-Process 的 -NoNewWindow 和 -Wait 参数，并重定向输出到实时显示
            try {
                # 方法1: 直接调用，让输出直接传递到控制台（最简单有效）
                # 设置输出编码为 UTF-8，避免中文乱码
                $OutputEncoding = [System.Text.Encoding]::UTF8
                [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
                
                # 直接执行 Python，输出会实时显示到控制台
                & $pythonExe $pythonArgs
                $exitCode = $LASTEXITCODE
                
                # 检查退出代码
                if ($exitCode -eq 0) {
                    Write-Host ""
                    Write-Log "========================================" "INFO"
                    Write-Log "✓ 数据同步流水线完成！" "SUCCESS"
                    Write-Log "  备份、导入、同步、聚合、清理全部完成" "SUCCESS"
                    Write-Log "========================================" "INFO"
                } else {
                    Write-Host ""
                    Write-Log "========================================" "INFO"
                    Write-Log "⚠ 数据同步流水线失败，但文件同步已成功" "WARNING"
                    Write-Log "  退出代码: $exitCode" "WARNING"
                    Write-Log "  请检查上面的错误信息" "WARNING"
                    Write-Log "  可以手动运行: python maintenance\data_sync_pipeline.py --excel $TargetPath" "WARNING"
                    Write-Log "========================================" "INFO"
                }
            } catch {
                Write-Host ""
                Write-Log "========================================" "INFO"
                Write-Log "⚠ 数据同步流水线执行出错: $_" "WARNING"
                Write-Log "  文件同步已成功，但需要手动运行数据同步流水线" "WARNING"
                Write-Log "  手动运行命令: python maintenance\data_sync_pipeline.py --excel $TargetPath" "WARNING"
                Write-Log "========================================" "INFO"
            }
        } catch {
            Write-Log "警告: 数据同步流水线初始化出错: $_" "WARNING"
            Write-Log "  文件同步已成功，但需要手动运行数据同步流水线" "WARNING"
        }
    }
    
    return ($failCount -eq 0)
}

# 执行主函数
try {
    $result = Sync-WeldingFiles
    if ($result) {
        exit 0
    } else {
        exit 1
    }
} catch {
    Write-Log "未处理的错误: $_" "ERROR"
    Write-Log "错误堆栈: $($_.ScriptStackTrace)" "ERROR"
    exit 1
}

