# PrecomControl SSL 证书生成脚本
# 支持域名和IP地址，自动检测OpenSSL，提供完整的证书生成功能

param(
    [Parameter(Mandatory=$false)]
    [string]$Domain = "",
    
    [Parameter(Mandatory=$false)]
    [string]$IP = "",
    
    [Parameter(Mandatory=$false)]
    [string]$NginxPath = "C:\nginx",
    
    [Parameter(Mandatory=$false)]
    [int]$ValidDays = 3650,
    
    [Parameter(Mandatory=$false)]
    [switch]$Force
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PrecomControl SSL 证书生成工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 确定证书名称（域名或IP）
$certName = ""
if ($Domain) {
    $certName = $Domain
    Write-Host "证书类型: 域名证书" -ForegroundColor Green
    Write-Host "域名: $Domain" -ForegroundColor Green
} elseif ($IP) {
    $certName = $IP
    Write-Host "证书类型: IP证书" -ForegroundColor Green
    Write-Host "IP地址: $IP" -ForegroundColor Green
} else {
    # 默认使用IP（内网部署）
    $certName = "10.78.44.3"
    Write-Host "证书类型: IP证书（默认）" -ForegroundColor Yellow
    Write-Host "IP地址: $certName" -ForegroundColor Yellow
    Write-Host "提示: 使用 -Domain 参数指定域名，或 -IP 参数指定IP地址" -ForegroundColor Gray
}

Write-Host "有效期: $ValidDays 天 ($([math]::Round($ValidDays/365, 1)) 年)" -ForegroundColor Green
Write-Host ""

# 创建SSL目录
$sslPath = "$NginxPath\ssl"
Write-Host "[1/4] 创建证书目录..." -ForegroundColor Yellow

if (-not (Test-Path $sslPath)) {
    try {
        New-Item -ItemType Directory -Path $sslPath -Force | Out-Null
        Write-Host "✓ 目录已创建: $sslPath" -ForegroundColor Green
    } catch {
        Write-Host "✗ 无法创建目录: $sslPath" -ForegroundColor Red
        Write-Host "  错误: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✓ 目录已存在: $sslPath" -ForegroundColor Green
}

# 证书文件路径
$certFile = "$sslPath\precom.crt"
$keyFile = "$sslPath\precom.key"

# 检查现有证书
Write-Host ""
Write-Host "[2/4] 检查现有证书..." -ForegroundColor Yellow

if ((Test-Path $certFile) -or (Test-Path $keyFile)) {
    if ($Force) {
        Write-Host "⚠ 强制模式：将覆盖现有证书" -ForegroundColor Yellow
    } else {
        Write-Host "⚠ 证书文件已存在" -ForegroundColor Yellow
        Write-Host "  证书文件: $certFile" -ForegroundColor Gray
        Write-Host "  私钥文件: $keyFile" -ForegroundColor Gray
        Write-Host ""
        
        $overwrite = Read-Host "是否覆盖现有证书? (Y/N)"
        if ($overwrite -ne "Y" -and $overwrite -ne "y") {
            Write-Host "操作已取消" -ForegroundColor Yellow
            exit 0
        }
    }
    
    # 备份现有证书
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    if (Test-Path $certFile) {
        $backupCert = "$certFile.backup.$timestamp"
        Copy-Item $certFile $backupCert -Force -ErrorAction SilentlyContinue
        Write-Host "✓ 已备份证书: $backupCert" -ForegroundColor Gray
    }
    if (Test-Path $keyFile) {
        $backupKey = "$keyFile.backup.$timestamp"
        Copy-Item $keyFile $backupKey -Force -ErrorAction SilentlyContinue
        Write-Host "✓ 已备份私钥: $backupKey" -ForegroundColor Gray
    }
}

# 检查OpenSSL
Write-Host ""
Write-Host "[3/4] 检测OpenSSL..." -ForegroundColor Yellow

$useOpenSSL = $false
$opensslPath = ""

# 检查系统PATH中的OpenSSL
try {
    $null = & openssl version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $opensslVersion = & openssl version 2>&1
        $useOpenSSL = $true
        $opensslPath = "openssl"
        Write-Host "✓ OpenSSL已找到: $opensslVersion" -ForegroundColor Green
    }
} catch {
    # 检查常见安装路径
    $commonPaths = @(
        "C:\OpenSSL-Win64\bin\openssl.exe",
        "C:\OpenSSL-Win32\bin\openssl.exe",
        "C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
        "C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe"
    )
    
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            $useOpenSSL = $true
            $opensslPath = $path
            $version = & $path version 2>&1
            Write-Host "✓ OpenSSL已找到: $version" -ForegroundColor Green
            Write-Host "  路径: $path" -ForegroundColor Gray
            break
        }
    }
}

if (-not $useOpenSSL) {
    Write-Host "⚠ OpenSSL未找到" -ForegroundColor Yellow
    Write-Host "  将使用PowerShell方法生成证书" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "提示: 安装OpenSSL可获得更好的兼容性" -ForegroundColor Gray
    Write-Host "  下载: https://slproweb.com/products/Win32OpenSSL.html" -ForegroundColor Gray
    Write-Host ""
}

# 生成证书
Write-Host ""
Write-Host "[4/4] 生成SSL证书..." -ForegroundColor Yellow

if ($useOpenSSL) {
    # 使用OpenSSL生成证书
    Write-Host "使用OpenSSL生成证书..." -ForegroundColor Cyan
    
    # 构建subject
    if ($Domain) {
        # 域名证书
        $subject = "/C=CN/ST=State/L=City/O=Organization/CN=$Domain"
    } else {
        # IP证书
        $subject = "/C=CN/ST=State/L=City/O=Organization/CN=$certName"
    }
    
    Write-Host "执行命令..." -ForegroundColor Gray
    
    if ($opensslPath -eq "openssl") {
        $result = & openssl req -x509 -nodes -days $ValidDays -newkey rsa:2048 -keyout $keyFile -out $certFile -subj $subject 2>&1
    } else {
        $result = & $opensslPath req -x509 -nodes -days $ValidDays -newkey rsa:2048 -keyout $keyFile -out $certFile -subj $subject 2>&1
    }
    
    if ($LASTEXITCODE -eq 0 -and (Test-Path $certFile) -and (Test-Path $keyFile)) {
        # 验证文件不为空
        $certSize = (Get-Item $certFile).Length
        $keySize = (Get-Item $keyFile).Length
        
        if ($certSize -gt 0 -and $keySize -gt 0) {
            Write-Host "✓ 证书生成成功！" -ForegroundColor Green
        } else {
            Write-Host "✗ 证书文件为空，尝试PowerShell方法..." -ForegroundColor Yellow
            $useOpenSSL = $false
        }
    } else {
        Write-Host "✗ OpenSSL生成失败，尝试PowerShell方法..." -ForegroundColor Yellow
        if ($result) {
            Write-Host "  错误信息: $result" -ForegroundColor Gray
        }
        $useOpenSSL = $false
    }
}

if (-not $useOpenSSL) {
    # 使用PowerShell生成证书
    Write-Host "使用PowerShell生成证书..." -ForegroundColor Cyan
    
    try {
        # 构建DNS名称列表
        $dnsNames = @()
        if ($Domain) {
            $dnsNames += $Domain
            $dnsNames += "www.$Domain"
        }
        if ($IP) {
            $dnsNames += $IP
        }
        if ($dnsNames.Count -eq 0) {
            $dnsNames = @($certName)
        }
        
        Write-Host "创建证书..." -ForegroundColor Gray
        
        # 创建自签名证书
        $cert = New-SelfSignedCertificate `
            -DnsName $dnsNames `
            -CertStoreLocation "cert:\LocalMachine\My" `
            -KeyAlgorithm RSA `
            -KeyLength 2048 `
            -NotAfter (Get-Date).AddDays($ValidDays) `
            -FriendlyName "PrecomControl SSL Certificate" `
            -KeyUsage DigitalSignature, KeyEncipherment `
            -KeyExportPolicy Exportable
        
        Write-Host "✓ 证书已创建到系统证书存储" -ForegroundColor Green
        
        # 导出证书
        Export-Certificate -Cert $cert -FilePath $certFile -Type CERT | Out-Null
        Write-Host "✓ 证书已导出: $certFile" -ForegroundColor Green
        
        # 尝试导出私钥
        Write-Host "导出私钥..." -ForegroundColor Gray
        
        $certPassword = ConvertTo-SecureString -String "temp_export_$(Get-Random)" -Force -AsPlainText
        $pfxPath = "$env:TEMP\precom_temp_$([Guid]::NewGuid().ToString('N').Substring(0,8)).pfx"
        
        Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $certPassword | Out-Null
        
        # 尝试使用OpenSSL从PFX提取私钥
        $opensslFound = $false
        $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($certPassword))
        
        if ($opensslPath -ne "") {
            try {
                if ($opensslPath -eq "openssl") {
                    $null = & openssl pkcs12 -in $pfxPath -nocerts -nodes -out $keyFile -passin "pass:$plainPassword" 2>&1
                } else {
                    $null = & $opensslPath pkcs12 -in $pfxPath -nocerts -nodes -out $keyFile -passin "pass:$plainPassword" 2>&1
                }
                if ($LASTEXITCODE -eq 0 -and (Test-Path $keyFile) -and (Get-Item $keyFile).Length -gt 0) {
                    $opensslFound = $true
                    Write-Host "✓ 私钥已导出: $keyFile" -ForegroundColor Green
                }
            } catch {
                # 忽略错误，继续
            }
        }
        
        if (-not $opensslFound) {
            Write-Host "⚠ 无法自动导出私钥文件" -ForegroundColor Yellow
            Write-Host "  证书已保存为PFX格式: $pfxPath" -ForegroundColor Gray
            Write-Host "  密码: $plainPassword" -ForegroundColor Gray
            Write-Host ""
            Write-Host "解决方案:" -ForegroundColor Yellow
            Write-Host "  1. 安装OpenSSL后重新运行此脚本" -ForegroundColor Gray
            Write-Host "  2. 或使用以下命令提取私钥:" -ForegroundColor Gray
            Write-Host "     openssl pkcs12 -in `"$pfxPath`" -nocerts -nodes -out `"$keyFile`" -passin pass:$plainPassword" -ForegroundColor Cyan
            
            # 创建占位符文件
            $placeholder = @"
# 私钥存储在Windows证书存储中
# 证书指纹: $($cert.Thumbprint)
# 
# 要提取私钥，请安装OpenSSL后运行:
# openssl pkcs12 -in "$pfxPath" -nocerts -nodes -out "$keyFile" -passin pass:$plainPassword
"@
            $placeholder | Out-File -FilePath $keyFile -Encoding UTF8
        }
        
        # 清理临时文件
        if (Test-Path $pfxPath) {
            Remove-Item $pfxPath -Force -ErrorAction SilentlyContinue
        }
        
        Write-Host ""
        Write-Host "信息: 证书已添加到系统证书存储" -ForegroundColor Gray
        Write-Host "      证书指纹: $($cert.Thumbprint)" -ForegroundColor Gray
        
    } catch {
        Write-Host "✗ 证书生成失败: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
        Write-Host "建议解决方案:" -ForegroundColor Yellow
        Write-Host "  1. 以管理员身份运行此脚本" -ForegroundColor Gray
        Write-Host "  2. 安装OpenSSL: https://slproweb.com/products/Win32OpenSSL.html" -ForegroundColor Gray
        exit 1
    }
}

# 验证证书文件
Write-Host ""
Write-Host "验证证书文件..." -ForegroundColor Yellow

$success = $true

if (Test-Path $certFile) {
    $certInfo = Get-Item $certFile
    if ($certInfo.Length -gt 0) {
        Write-Host "✓ 证书文件: $certFile" -ForegroundColor Green
        Write-Host "  大小: $([math]::Round($certInfo.Length/1KB, 2)) KB" -ForegroundColor Gray
    } else {
        Write-Host "✗ 证书文件为空" -ForegroundColor Red
        $success = $false
    }
} else {
    Write-Host "✗ 证书文件未找到" -ForegroundColor Red
    $success = $false
}

if (Test-Path $keyFile) {
    $keyInfo = Get-Item $keyFile
    if ($keyInfo.Length -gt 100) {
        Write-Host "✓ 私钥文件: $keyFile" -ForegroundColor Green
        Write-Host "  大小: $([math]::Round($keyInfo.Length/1KB, 2)) KB" -ForegroundColor Gray
    } else {
        Write-Host "⚠ 私钥文件可能不完整（可能存储在系统证书存储中）" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠ 私钥文件未找到（可能存储在系统证书存储中）" -ForegroundColor Yellow
}

# 显示证书信息
if ($success -and $useOpenSSL -and (Test-Path $certFile)) {
    Write-Host ""
    Write-Host "证书详细信息:" -ForegroundColor Cyan
    
    if ($opensslPath -eq "openssl") {
        $certDetails = & openssl x509 -in $certFile -text -noout 2>&1
    } else {
        $certDetails = & $opensslPath x509 -in $certFile -text -noout 2>&1
    }
    
    $certDetails | Select-String -Pattern "Subject:|Issuer:|Not Before|Not After|DNS:|IP Address:" | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
}

# 完成
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($success) {
    Write-Host "✓ 证书生成完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "证书文件位置:" -ForegroundColor White
    Write-Host "  证书: $certFile" -ForegroundColor Gray
    if ((Test-Path $keyFile) -and ((Get-Item $keyFile).Length -gt 100)) {
        Write-Host "  私钥: $keyFile" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "下一步操作:" -ForegroundColor White
    Write-Host "  1. 确认Nginx配置中的证书路径正确" -ForegroundColor Gray
    Write-Host "     当前配置: ssl_certificate C:/nginx/ssl/precom.crt" -ForegroundColor Cyan
    Write-Host "     当前配置: ssl_certificate_key C:/nginx/ssl/precom.key" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  2. 测试Nginx配置:" -ForegroundColor Gray
    Write-Host "     C:\nginx\nginx.exe -t" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  3. 重载Nginx配置:" -ForegroundColor Gray
    Write-Host "     C:\nginx\nginx.exe -s reload" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "⚠ 注意: 这是自签名证书" -ForegroundColor Yellow
    Write-Host "   浏览器会显示安全警告，点击'高级' -> '继续访问'即可" -ForegroundColor Yellow
    Write-Host "   生产环境建议使用正式SSL证书（Let's Encrypt或购买）" -ForegroundColor Yellow
} else {
    Write-Host "✗ 证书生成失败" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "请检查错误信息并重试" -ForegroundColor Yellow
}
Write-Host ""



