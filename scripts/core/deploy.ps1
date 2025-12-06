# PrecomControl 统一部署脚本
# 整合所有部署功能：Nginx配置、证书生成、防火墙、服务启动

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("quick", "standard", "full")]
    [string]$Mode = "standard",
    
    [Parameter(Mandatory=$false)]
    [string]$Domain = "",
    
    [Parameter(Mandatory=$false)]
    [string]$IP = "",
    
    [Parameter(Mandatory=$false)]
    [string]$NginxPath = "C:\nginx",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipCert,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipFirewall
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PrecomControl 统一部署脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查管理员权限
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "⚠ 警告: 未以管理员权限运行" -ForegroundColor Yellow
    Write-Host "  某些功能（防火墙、Nginx服务）可能需要管理员权限" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "是否继续? (Y/N)"
    if ($continue -ne "Y" -and $continue -ne "y") {
        exit 0
    }
}

# 获取脚本所在目录（scripts/core）
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
# 获取项目根目录（scripts/core 的父目录的父目录）
$projectRoot = Split-Path -Parent (Split-Path -Parent $scriptPath)
Set-Location $projectRoot

# 快速部署模式
if ($Mode -eq "quick") {
    Write-Host "模式: 快速部署（无需Nginx）" -ForegroundColor Cyan
    Write-Host ""
    
    # 检查Python
    Write-Host "[1/3] 检查Python环境..." -ForegroundColor Yellow
    try {
        python --version | Out-Null
        Write-Host "✓ Python已安装" -ForegroundColor Green
    } catch {
        Write-Host "✗ Python未安装" -ForegroundColor Red
        exit 1
    }
    
    # 安装依赖
    Write-Host ""
    Write-Host "[2/3] 安装依赖..." -ForegroundColor Yellow
    pip install waitress pyopenssl --quiet
    Write-Host "✓ 依赖安装完成" -ForegroundColor Green
    
    # 生成证书（如果不存在）
    Write-Host ""
    Write-Host "[3/3] 配置SSL证书..." -ForegroundColor Yellow
    if (-not (Test-Path "ssl\cert.pem")) {
        Write-Host "生成自签名证书..." -ForegroundColor Gray
        python -c "from OpenSSL import crypto; import os; os.makedirs('ssl', exist_ok=True); key = crypto.PKey(); key.generate_key(crypto.TYPE_RSA, 2048); cert = crypto.X509(); cert.get_subject().CN = 'localhost'; cert.set_serial_number(1000); cert.gmtime_adj_notBefore(0); cert.gmtime_adj_notAfter(365*24*60*60*10); cert.set_issuer(cert.get_subject()); cert.set_pubkey(key); cert.sign(key, 'sha256'); open('ssl/cert.pem', 'wb').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert)); open('ssl/key.pem', 'wb').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key)); print('证书生成成功')"
        Write-Host "✓ 证书生成完成" -ForegroundColor Green
    } else {
        Write-Host "✓ 证书已存在" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "快速部署完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "启动应用:" -ForegroundColor White
    Write-Host "  .\scripts\core\start.ps1 -Mode production -HTTPS" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "访问地址:" -ForegroundColor White
    Write-Host "  https://localhost:5000" -ForegroundColor Cyan
    Write-Host ""
    exit 0
}

# 标准/完整部署模式
Write-Host "模式: $Mode 部署（Nginx + HTTPS）" -ForegroundColor Cyan
Write-Host ""

# 1. 检查Nginx
Write-Host "[1/8] 检查Nginx..." -ForegroundColor Yellow
if (Test-Path "$NginxPath\nginx.exe") {
    $nginxVersion = & "$NginxPath\nginx.exe" -v 2>&1
    Write-Host "✓ Nginx已安装: $nginxVersion" -ForegroundColor Green
} else {
    Write-Host "✗ 未找到Nginx" -ForegroundColor Red
    Write-Host "  请下载并解压到: $NginxPath" -ForegroundColor Yellow
    Write-Host "  下载地址: http://nginx.org/en/download.html" -ForegroundColor Yellow
    exit 1
}

# 2. 创建SSL目录
Write-Host ""
Write-Host "[2/8] 创建SSL证书目录..." -ForegroundColor Yellow
$sslPath = "$NginxPath\ssl"
if (-not (Test-Path $sslPath)) {
    New-Item -ItemType Directory -Path $sslPath -Force | Out-Null
    Write-Host "✓ 目录已创建: $sslPath" -ForegroundColor Green
} else {
    Write-Host "✓ 目录已存在: $sslPath" -ForegroundColor Green
}

# 3. 生成证书
if (-not $SkipCert) {
    Write-Host ""
    Write-Host "[3/8] 生成SSL证书..." -ForegroundColor Yellow
    
    $certScript = Join-Path $scriptPath "generate_cert.ps1"
    if (Test-Path $certScript) {
        if ($Domain) {
            & $certScript -Domain $Domain -NginxPath $NginxPath
        } elseif ($IP) {
            & $certScript -IP $IP -NginxPath $NginxPath
        } else {
            & $certScript -IP "10.78.44.3" -NginxPath $NginxPath
        }
    } else {
        Write-Host "⚠ 证书生成脚本未找到，跳过证书生成" -ForegroundColor Yellow
        Write-Host "  请手动运行: .\scripts\core\generate_cert.ps1" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "[3/8] 跳过证书生成..." -ForegroundColor Yellow
    Write-Host "✓ 使用现有证书" -ForegroundColor Green
}

# 4. 复制Nginx配置
Write-Host ""
Write-Host "[4/8] 配置Nginx..." -ForegroundColor Yellow
$confSource = Join-Path $projectRoot "nginx\nginx_precom.conf"
$confTarget = "$NginxPath\conf\precom.conf"

if (Test-Path $confSource) {
    Copy-Item $confSource $confTarget -Force
    Write-Host "✓ 配置文件已复制: $confTarget" -ForegroundColor Green
} else {
    Write-Host "✗ 配置文件不存在: $confSource" -ForegroundColor Red
    exit 1
}

# 检查主配置文件
$nginxConf = "$NginxPath\conf\nginx.conf"
if (Test-Path $nginxConf) {
    $includeExists = Select-String -Path $nginxConf -Pattern "include\s+precom\.conf" -Quiet
    if (-not $includeExists) {
        Write-Host "⚠ 需要在nginx.conf中添加: include precom.conf;" -ForegroundColor Yellow
        Write-Host "  配置文件: $nginxConf" -ForegroundColor Gray
    } else {
        Write-Host "✓ Nginx主配置已包含precom.conf" -ForegroundColor Green
    }
}

# 5. 测试Nginx配置
Write-Host ""
Write-Host "[5/8] 测试Nginx配置..." -ForegroundColor Yellow
Push-Location $NginxPath
try {
    & ".\nginx.exe" -t 2>&1 | ForEach-Object { Write-Host $_ }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Nginx配置测试失败" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Write-Host "✓ Nginx配置测试通过" -ForegroundColor Green
} finally {
    Pop-Location
}

# 6. 配置防火墙
if (-not $SkipFirewall -and $isAdmin) {
    Write-Host ""
    Write-Host "[6/8] 配置防火墙规则..." -ForegroundColor Yellow
    
    $httpRule = Get-NetFirewallRule -DisplayName "Precom HTTP" -ErrorAction SilentlyContinue
    $httpsRule = Get-NetFirewallRule -DisplayName "Precom HTTPS" -ErrorAction SilentlyContinue
    
    if (-not $httpRule) {
        New-NetFirewallRule -DisplayName "Precom HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow | Out-Null
        Write-Host "✓ 已开放HTTP端口(80)" -ForegroundColor Green
    } else {
        Write-Host "✓ HTTP端口规则已存在" -ForegroundColor Green
    }
    
    if (-not $httpsRule) {
        New-NetFirewallRule -DisplayName "Precom HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow | Out-Null
        Write-Host "✓ 已开放HTTPS端口(443)" -ForegroundColor Green
    } else {
        Write-Host "✓ HTTPS端口规则已存在" -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "[6/8] 跳过防火墙配置..." -ForegroundColor Yellow
    if (-not $isAdmin) {
        Write-Host "⚠ 需要管理员权限配置防火墙" -ForegroundColor Yellow
    }
}

# 7. 启动Nginx
Write-Host ""
Write-Host "[7/8] 启动Nginx服务..." -ForegroundColor Yellow
$nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue

if ($nginxProcess) {
    Write-Host "重新加载Nginx配置..." -ForegroundColor Gray
    Push-Location $NginxPath
    try {
        & ".\nginx.exe" -s reload
        Write-Host "✓ Nginx已重新加载" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host "启动Nginx..." -ForegroundColor Gray
    Start-Process -FilePath "$NginxPath\nginx.exe" -WorkingDirectory $NginxPath -WindowStyle Hidden
    Start-Sleep -Seconds 2
    
    $nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue
    if ($nginxProcess) {
        Write-Host "✓ Nginx已启动" -ForegroundColor Green
    } else {
        Write-Host "✗ Nginx启动失败" -ForegroundColor Red
        exit 1
    }
}

# 8. 检查Flask应用
Write-Host ""
Write-Host "[8/8] 检查Flask应用..." -ForegroundColor Yellow
$flaskPort = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue

if ($flaskPort) {
    Write-Host "✓ Flask应用已运行(端口5000)" -ForegroundColor Green
} else {
    Write-Host "⚠ Flask应用未运行" -ForegroundColor Yellow
    Write-Host "  请运行: .\scripts\core\start.ps1" -ForegroundColor Cyan
}

# 完成
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "部署完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 确定访问地址
$accessUrl = ""
if ($Domain) {
    $accessUrl = $Domain
} elseif ($IP) {
    $accessUrl = $IP
} else {
    $accessUrl = "localhost"
}

Write-Host "访问地址:" -ForegroundColor White
Write-Host "  HTTP:  http://$accessUrl" -ForegroundColor Cyan
Write-Host "  HTTPS: https://$accessUrl" -ForegroundColor Cyan
Write-Host ""

Write-Host "管理命令:" -ForegroundColor White
    Write-Host "  启动应用: .\scripts\core\start.ps1" -ForegroundColor Gray
Write-Host "  检查状态: .\check_deployment.ps1" -ForegroundColor Gray
Write-Host "  重载Nginx: $NginxPath\nginx.exe -s reload" -ForegroundColor Gray
Write-Host "  停止Nginx: $NginxPath\nginx.exe -s stop" -ForegroundColor Gray
Write-Host ""

if (-not $Domain -and -not $IP) {
    Write-Host "⚠ 注意: 使用自签名证书，浏览器会显示安全警告" -ForegroundColor Yellow
    Write-Host "  点击'高级' -> '继续访问'即可" -ForegroundColor Yellow
}

Write-Host ""

