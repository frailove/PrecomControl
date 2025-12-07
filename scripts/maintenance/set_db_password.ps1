# 使用 Windows DPAPI 加密存储数据库密码
# 功能：将数据库密码加密后存储在本地文件中，供定时任务使用
# 安全：使用 Windows DPAPI，只有当前用户或机器可以解密

param(
    [Parameter(Mandatory=$false)]
    [switch]$Remove,  # 删除加密的密码文件
    
    [Parameter(Mandatory=$false)]
    [switch]$Show  # 显示是否已设置（不显示密码值）
)

# 加载必要的 .NET 程序集
Add-Type -AssemblyName System.Security

$PasswordFile = "$PSScriptRoot\..\..\config\db_password.encrypted"
$ConfigDir = Split-Path -Parent $PasswordFile

# 显示当前设置
if ($Show) {
    if (Test-Path $PasswordFile) {
        Write-Host "✓ 加密密码文件已存在" -ForegroundColor Green
        Write-Host "  文件路径: $PasswordFile" -ForegroundColor Gray
        Write-Host "  (密码已加密，无法直接查看)" -ForegroundColor Gray
        
        # 尝试解密以验证文件是否有效
        try {
            $encrypted = Get-Content $PasswordFile -Raw
            $encryptedBytes = [Convert]::FromBase64String($encrypted)
            $decryptedBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
                $encryptedBytes,
                $null,
                [System.Security.Cryptography.DataProtectionScope]::CurrentUser
            )
            $passwordLength = ([System.Text.Encoding]::UTF8.GetString($decryptedBytes)).Length
            Write-Host "  密码长度: $passwordLength 字符" -ForegroundColor Gray
            Write-Host "  状态: 有效" -ForegroundColor Green
        } catch {
            Write-Host "  状态: 文件已损坏或无法解密" -ForegroundColor Red
        }
    } else {
        Write-Host "✗ 加密密码文件不存在" -ForegroundColor Yellow
        Write-Host "  文件路径: $PasswordFile" -ForegroundColor Gray
    }
    exit 0
}

# 删除加密文件
if ($Remove) {
    Write-Host "正在删除加密密码文件..." -ForegroundColor Yellow
    if (Test-Path $PasswordFile) {
        try {
            Remove-Item $PasswordFile -Force
            Write-Host "OK: Encrypted password file deleted" -ForegroundColor Green
        } catch {
            Write-Host "错误: 删除文件失败: $_" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "文件不存在，无需删除" -ForegroundColor Yellow
    }
    exit 0
}

# 设置密码
Write-Host "使用 Windows DPAPI 加密存储数据库密码" -ForegroundColor Cyan
Write-Host "存储位置: $PasswordFile" -ForegroundColor Gray
Write-Host ""
Write-Host "请输入MySQL数据库密码:" -ForegroundColor Cyan
Write-Host "(密码输入时不会显示，输入完成后按回车)" -ForegroundColor Gray

# 使用 SecureString 读取密码（不在屏幕上显示）
Write-Host "数据库密码: " -NoNewline -ForegroundColor Cyan
$securePassword = Read-Host -AsSecureString

# 将 SecureString 转换为普通字符串
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

if ([string]::IsNullOrWhiteSpace($plainPassword)) {
    Write-Host "错误: 密码不能为空" -ForegroundColor Red
    exit 1
}

# 确保配置目录存在
if (-not (Test-Path $ConfigDir)) {
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
}

# 使用 Windows DPAPI 加密密码
try {
    # 将密码转换为字节数组
    $passwordBytes = [System.Text.Encoding]::UTF8.GetBytes($plainPassword)
    
    # 使用 DPAPI 加密（CurrentUser 范围，只有当前用户可以解密）
    $encryptedBytes = [System.Security.Cryptography.ProtectedData]::Protect(
        $passwordBytes,
        $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    
    # 将加密后的字节数组转换为 Base64 字符串并保存
    $encryptedString = [Convert]::ToBase64String($encryptedBytes)
    $encryptedString | Out-File -FilePath $PasswordFile -Encoding ASCII -NoNewline -Force
    
    # 设置文件权限（仅当前用户可以访问）
    $acl = Get-Acl $PasswordFile
    $acl.SetAccessRuleProtection($true, $false)  # 禁用继承
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $currentUser,
        "FullControl",
        "Allow"
    )
    $acl.SetAccessRule($accessRule)
    Set-Acl $PasswordFile $acl
    
    Write-Host ""
    Write-Host "✓ 密码已加密并安全存储！" -ForegroundColor Green
    Write-Host ""
    Write-Host "安全说明:" -ForegroundColor Yellow
    Write-Host "  1. 密码使用 Windows DPAPI 加密，只有当前用户可以解密" -ForegroundColor Gray
    Write-Host "  2. 加密文件存储在: $PasswordFile" -ForegroundColor Gray
    Write-Host "  3. 定时任务可以自动读取此加密密码，无需手动输入" -ForegroundColor Gray
    Write-Host "  4. 如果修改了数据库密码，需要重新运行此脚本更新" -ForegroundColor Gray
    Write-Host ""
    Write-Host "验证设置:" -ForegroundColor Cyan
    Write-Host "  .\scripts\maintenance\set_db_password.ps1 -Show" -ForegroundColor Gray
} catch {
    Write-Host "错误: 加密存储密码失败: $_" -ForegroundColor Red
    exit 1
}
