# PrecomControl 统一启动脚本
# 支持多种启动模式：开发、生产、服务

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("dev", "production", "service")]
    [string]$Mode = "production",
    
    [Parameter(Mandatory=$false)]
    [string]$HostAddress = "0.0.0.0",
    
    [Parameter(Mandatory=$false)]
    [int]$Port = 5000,  # 固定使用5000端口，不占用其他端口（8000、8203、8206等）
    
    [Parameter(Mandatory=$false)]
    [int]$Threads = 8,
    
    [Parameter(Mandatory=$false)]
    [switch]$HTTPS,
    
    [Parameter(Mandatory=$false)]
    [SecureString]$DbPassword  # 数据库密码（可选，SecureString类型，如果不提供则交互式输入）
)

# 强制使用5000端口（确保不占用其他应用端口）
$Port = 5000
$HostAddress = "0.0.0.0"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PrecomControl 系统启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 获取脚本所在目录（scripts/core）
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
# 获取项目根目录（scripts/core 的父目录的父目录）
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptPath)
Set-Location $projectRoot

# 创建日志目录
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
    Write-Host "✓ 创建日志目录" -ForegroundColor Green
}

# 自动激活虚拟环境（如果存在）
Write-Host "[0/5] 检查虚拟环境..." -ForegroundColor Yellow
$venvPaths = @("myenv", "venv")
$venvActivated = $false

foreach ($venvPath in $venvPaths) {
    $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        Write-Host "✓ 找到虚拟环境: $venvPath" -ForegroundColor Green
        Write-Host "  正在激活虚拟环境..." -ForegroundColor Gray
        & $activateScript
        $venvActivated = $true
        Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
        break
    }
}

if (-not $venvActivated) {
    Write-Host "⚠ 未找到虚拟环境，使用系统Python" -ForegroundColor Yellow
    Write-Host "  建议创建虚拟环境: python -m venv myenv" -ForegroundColor Gray
}

# 检查Python环境
Write-Host ""
Write-Host "[1/5] 检查Python环境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    $pythonPath = (Get-Command python).Source
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
    Write-Host "  Python路径: $pythonPath" -ForegroundColor Gray
} catch {
    Write-Host "✗ Python未安装或未添加到PATH" -ForegroundColor Red
    Write-Host "  请先安装Python 3.7+" -ForegroundColor Yellow
    exit 1
}

# 检查依赖
Write-Host ""
Write-Host "[2/5] 检查依赖包..." -ForegroundColor Yellow

# 检查关键依赖包
$requiredPackages = @("flask", "waitress", "mysql-connector-python", "pandas")
$missingPackages = @()

foreach ($pkg in $requiredPackages) {
    pip show $pkg 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $missingPackages += $pkg
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host "⚠ 缺少依赖包: $($missingPackages -join ', ')" -ForegroundColor Yellow
    Write-Host "  正在安装到虚拟环境..." -ForegroundColor Yellow
    
    # 优先使用 requirements.txt 安装所有依赖（确保在虚拟环境中安装）
    if (Test-Path "requirements.txt") {
        Write-Host "  使用 requirements.txt 安装所有依赖..." -ForegroundColor Gray
        python -m pip install -r requirements.txt
    } else {
        Write-Host "  安装缺失的依赖包..." -ForegroundColor Gray
        python -m pip install $missingPackages
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ 依赖安装失败" -ForegroundColor Red
        Write-Host "  请手动运行: python -m pip install -r requirements.txt" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✓ 依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "✓ 所有依赖已安装" -ForegroundColor Green
}

# 检查端口占用
Write-Host ""
Write-Host "[3/6] 检查端口占用..." -ForegroundColor Yellow

# 检查5000端口是否被占用
$port5000 = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($port5000) {
    Write-Host "⚠ 端口5000已被占用" -ForegroundColor Yellow
    Write-Host "  占用进程: $($port5000 | Select-Object -First 1 | ForEach-Object { (Get-Process -Id $_.OwningProcess).ProcessName })" -ForegroundColor Gray
    Write-Host "  请先停止占用5000端口的进程，或检查是否已有实例在运行" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "是否继续启动? (Y/N)"
    if ($continue -ne "Y" -and $continue -ne "y") {
        exit 0
    }
} else {
    Write-Host "✓ 端口5000可用" -ForegroundColor Green
}

# 检查其他端口（确保不会占用）
$protectedPorts = @(8000, 8203, 8206)
$conflictPorts = @()
foreach ($port in $protectedPorts) {
    $portCheck = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($portCheck) {
        $conflictPorts += $port
    }
}

if ($conflictPorts.Count -gt 0) {
    Write-Host "⚠ 检测到其他应用正在使用端口: $($conflictPorts -join ', ')" -ForegroundColor Yellow
    Write-Host "  本应用仅使用5000端口，不会占用这些端口" -ForegroundColor Green
} else {
    Write-Host "✓ 其他应用端口正常（8000、8203、8206未占用）" -ForegroundColor Green
}

# 检查并设置数据库密码
Write-Host ""
Write-Host "[4/6] 检查数据库配置..." -ForegroundColor Yellow

# 检查并设置数据库密码环境变量
if (-not $env:DB_PASSWORD) {
    if ($DbPassword) {
        # 如果通过参数传递了密码（SecureString），转换为普通字符串
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($DbPassword)
        $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        $env:DB_PASSWORD = $plainPassword
        Write-Host "✓ 数据库密码已从参数设置（仅当前会话有效）" -ForegroundColor Green
    } else {
        # 交互式输入密码
        Write-Host "⚠ 未检测到数据库密码环境变量 (DB_PASSWORD)" -ForegroundColor Yellow
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
        
        # 设置环境变量（仅当前会话有效）
        $env:DB_PASSWORD = $plainPassword
        Write-Host "✓ 数据库密码已设置（仅当前会话有效）" -ForegroundColor Green
        Write-Host ""
    }
} else {
    Write-Host "✓ 数据库密码环境变量已设置" -ForegroundColor Green
}

# 检查数据库连接
Write-Host "  正在测试数据库连接..." -ForegroundColor Gray
try {
    $dbTest = python -c "from database import get_db_connection; conn = get_db_connection(); print('OK' if conn else 'FAIL')" 2>&1
    if ($dbTest -match "OK") {
        Write-Host "✓ 数据库连接正常" -ForegroundColor Green
    } else {
        Write-Host "⚠ 数据库连接失败，但将继续启动" -ForegroundColor Yellow
        Write-Host "  错误: $dbTest" -ForegroundColor Gray
        Write-Host ""
        Write-Host "提示: 如果密码错误，请重新运行脚本并输入正确密码" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠ 无法测试数据库连接" -ForegroundColor Yellow
}

# 启动应用
Write-Host ""
Write-Host "[5/6] 启动应用服务器..." -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠ 重要: 本应用固定使用端口5000，不会占用其他端口（8000、8203、8206等）" -ForegroundColor Cyan
Write-Host ""

switch ($Mode) {
    "dev" {
        # 开发模式 - 使用Flask内置服务器
        Write-Host "模式: 开发模式（Flask内置服务器）" -ForegroundColor Cyan
        Write-Host "访问地址: http://${HostAddress}:${Port}" -ForegroundColor Green
        Write-Host ""
        Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Yellow
        Write-Host ""
        
        $env:FLASK_ENV = "development"
        $env:FLASK_DEBUG = "1"
        python app.py
    }
    
    "production" {
        # 生产模式 - 使用Waitress
        # 强制使用5000端口（防止被参数或环境变量覆盖）
        $Port = 5000
        $HostAddress = "0.0.0.0"
        
        Write-Host "模式: 生产模式（Waitress WSGI服务器）" -ForegroundColor Cyan
        Write-Host "监听地址: ${HostAddress}:${Port}" -ForegroundColor Green
        Write-Host "线程数: $Threads" -ForegroundColor Green
        
        if ($HTTPS) {
            Write-Host "协议: HTTPS" -ForegroundColor Green
            Write-Host "访问地址: https://${HostAddress}:${Port}" -ForegroundColor Green
        } else {
            Write-Host "协议: HTTP" -ForegroundColor Green
            Write-Host "访问地址: http://${HostAddress}:${Port}" -ForegroundColor Green
        }
        
        Write-Host ""
        Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Yellow
        Write-Host ""
        
        if ($HTTPS) {
            # HTTPS模式（需要证书）
            $certFile = "ssl\cert.pem"
            $keyFile = "ssl\key.pem"
            
            if (-not ((Test-Path $certFile) -and (Test-Path $keyFile))) {
                Write-Host "⚠ 未找到SSL证书文件" -ForegroundColor Yellow
                Write-Host "  证书文件: $certFile" -ForegroundColor Gray
                Write-Host "  私钥文件: $keyFile" -ForegroundColor Gray
                Write-Host ""
                Write-Host "请先运行证书生成脚本或使用HTTP模式" -ForegroundColor Yellow
                exit 1
            }
            
            python -m waitress --listen=${HostAddress}:5000 --threads=$Threads --url-scheme=https wsgi:app
        } else {
            python -m waitress --listen=${HostAddress}:5000 --threads=$Threads wsgi:app
        }
    }
    
    "service" {
        # 服务模式 - 用于NSSM注册为Windows服务
        # 强制使用5000端口
        $Port = 5000
        
        Write-Host "模式: 服务模式（后台运行）" -ForegroundColor Cyan
        Write-Host "监听地址: 127.0.0.1:5000" -ForegroundColor Green
        Write-Host "线程数: 16" -ForegroundColor Green
        Write-Host ""
        Write-Host "此模式用于注册为Windows服务" -ForegroundColor Gray
        Write-Host "日志将写入 logs\ 目录" -ForegroundColor Gray
        Write-Host ""
        
        python -m waitress --listen=127.0.0.1:5000 --threads=16 --channel-timeout=120 wsgi:app
    }
}


