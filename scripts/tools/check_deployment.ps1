# 部署状态检查脚本
# 检查系统各组件运行状态

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "预试车管理系统 - 部署状态检查" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allOK = $true

# 1. 检查 Python
Write-Host "[1] Python 环境" -ForegroundColor Green
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python 未安装" -ForegroundColor Red
    $allOK = $false
}

# 2. 检查依赖包
Write-Host ""
Write-Host "[2] Python 依赖包" -ForegroundColor Green
$packages = @("flask", "waitress", "pymysql", "flask-babel")
foreach ($pkg in $packages) {
    $installed = pip show $pkg 2>&1 | Out-Null; $?
    if ($installed) {
        $version = pip show $pkg 2>&1 | Select-String "Version:" | ForEach-Object { $_.ToString().Split(":")[1].Trim() }
        Write-Host "  ✓ $pkg ($version)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $pkg 未安装" -ForegroundColor Red
        $allOK = $false
    }
}

# 3. 检查数据库连接
Write-Host ""
Write-Host "[3] 数据库连接" -ForegroundColor Green
try {
    $testResult = python -c "from database import get_db_connection; conn = get_db_connection(); print('OK') if conn else print('FAIL')" 2>&1
    if ($testResult -match "OK") {
        Write-Host "  ✓ 数据库连接正常" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 数据库连接失败: $testResult" -ForegroundColor Red
        $allOK = $false
    }
} catch {
    Write-Host "  ✗ 数据库连接测试失败" -ForegroundColor Red
    $allOK = $false
}

# 4. 检查 Flask 应用
Write-Host ""
Write-Host "[4] Flask 应用服务" -ForegroundColor Green
$flaskPort = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($flaskPort) {
    Write-Host "  ✓ Flask 应用运行中 (端口 5000)" -ForegroundColor Green
    
    # 测试健康检查
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host "  ✓ 健康检查通过" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠ 健康检查失败" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✗ Flask 应用未运行" -ForegroundColor Red
    Write-Host "    运行: .\scripts\core\start.ps1 -Mode production" -ForegroundColor Yellow
    $allOK = $false
}

# 5. 检查 Nginx
Write-Host ""
Write-Host "[5] Nginx 服务" -ForegroundColor Green
$nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue
if ($nginxProcess) {
    Write-Host "  ✓ Nginx 运行中 (进程数: $($nginxProcess.Count))" -ForegroundColor Green
    
    # 检查端口
    $port80 = Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue
    $port443 = Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue
    
    if ($port80) {
        Write-Host "  ✓ HTTP 端口 (80) 已监听" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ HTTP 端口 (80) 未监听" -ForegroundColor Yellow
    }
    
    if ($port443) {
        Write-Host "  ✓ HTTPS 端口 (443) 已监听" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ HTTPS 端口 (443) 未监听" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠ Nginx 未运行（可选组件）" -ForegroundColor Yellow
}

# 6. 检查防火墙规则
Write-Host ""
Write-Host "[6] 防火墙规则" -ForegroundColor Green
$httpRule = Get-NetFirewallRule -DisplayName "Precom HTTP" -ErrorAction SilentlyContinue
$httpsRule = Get-NetFirewallRule -DisplayName "Precom HTTPS" -ErrorAction SilentlyContinue

if ($httpRule -and $httpRule.Enabled) {
    Write-Host "  ✓ HTTP 规则已启用" -ForegroundColor Green
} else {
    Write-Host "  ⚠ HTTP 规则未配置" -ForegroundColor Yellow
}

if ($httpsRule -and $httpsRule.Enabled) {
    Write-Host "  ✓ HTTPS 规则已启用" -ForegroundColor Green
} else {
    Write-Host "  ⚠ HTTPS 规则未配置" -ForegroundColor Yellow
}

# 7. 检查 SSL 证书
Write-Host ""
Write-Host "[7] SSL 证书" -ForegroundColor Green
$nginxSsl = "C:\nginx\ssl"
$localSsl = ".\ssl"

if (Test-Path "$nginxSsl\precom.crt" -and Test-Path "$nginxSsl\precom.key") {
    Write-Host "  ✓ Nginx SSL 证书已配置" -ForegroundColor Green
    Write-Host "    $nginxSsl\precom.crt" -ForegroundColor Gray
} elseif (Test-Path "$localSsl\cert.pem" -and Test-Path "$localSsl\key.pem") {
    Write-Host "  ✓ 本地 SSL 证书已配置" -ForegroundColor Green
    Write-Host "    $localSsl\cert.pem" -ForegroundColor Gray
} else {
    Write-Host "  ⚠ SSL 证书未配置" -ForegroundColor Yellow
}

# 8. 检查日志文件
Write-Host ""
Write-Host "[8] 日志文件" -ForegroundColor Green
$logFiles = @(
    ".\logs\app.log",
    ".\logs\gunicorn_error.log",
    "C:\nginx\logs\error.log"
)

foreach ($logFile in $logFiles) {
    if (Test-Path $logFile) {
        $size = (Get-Item $logFile).Length / 1KB
        Write-Host "  ✓ $logFile ($([math]::Round($size, 2)) KB)" -ForegroundColor Green
    }
}

# 9. 检查配置文件
Write-Host ""
Write-Host "[9] 配置文件" -ForegroundColor Green
$configFiles = @(
    ".\config.py",
    ".\wsgi.py",
    "C:\nginx\conf\precom.conf"
)

foreach ($configFile in $configFiles) {
    if (Test-Path $configFile) {
        Write-Host "  ✓ $configFile" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $configFile 不存在" -ForegroundColor Yellow
    }
}

# 10. 网络连通性测试
Write-Host ""
Write-Host "[10] 网络连通性" -ForegroundColor Green

# 测试本地连接
$tests = @(
    @{Url="http://localhost:5000/health"; Name="Flask HTTP"},
    @{Url="http://localhost/health"; Name="Nginx HTTP"},
    @{Url="https://localhost/health"; Name="Nginx HTTPS"}
)

foreach ($test in $tests) {
    try {
        $response = Invoke-WebRequest -Uri $test.Url -UseBasicParsing -TimeoutSec 3 2>&1
        if ($response.StatusCode -eq 200) {
            Write-Host "  ✓ $($test.Name) - OK" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ $($test.Name) - 状态码: $($response.StatusCode)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ✗ $($test.Name) - 无法连接" -ForegroundColor Red
    }
}

# 总结
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($allOK) {
    Write-Host "状态: 所有核心组件正常 ✓" -ForegroundColor Green
} else {
    Write-Host "状态: 存在问题需要修复 ✗" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 显示系统信息
Write-Host "系统信息:" -ForegroundColor White
Write-Host "  主机名: $env:COMPUTERNAME" -ForegroundColor Gray
Write-Host "  用户: $env:USERNAME" -ForegroundColor Gray
Write-Host "  时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# 显示IP地址
Write-Host ""
Write-Host "IP 地址:" -ForegroundColor White
Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -ne "127.0.0.1"} | ForEach-Object {
    Write-Host "  $($_.InterfaceAlias): $($_.IPAddress)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')

