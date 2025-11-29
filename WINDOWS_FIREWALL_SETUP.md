# Windows 防火墙配置指南

## 问题描述

当 Flask 应用运行在服务器上，从本地电脑访问时：
- ✅ GET 请求正常（可以打开网页、下载文件）
- ✅ POST 请求正常（可以上传文件）
- ❌ PUT/DELETE 请求失败（不能删除、不能保存修改）

这是因为 Windows 防火墙可能对某些 HTTP 方法有特殊限制，或者连接在响应传输时被重置。

## 解决方案

### 方法 1：使用 PowerShell 脚本（推荐）

#### 步骤 1：检查当前防火墙规则

在服务器上，以**管理员身份**运行 PowerShell，执行：

```powershell
# 检查端口 5000 的防火墙规则
.\check_firewall.ps1
```

#### 步骤 2：添加防火墙规则

如果检查发现没有规则，执行：

```powershell
# 添加防火墙规则（允许端口 5000 的入站连接）
.\add_firewall_rule.ps1
```

### 方法 2：手动配置防火墙（图形界面）

#### 步骤 1：打开防火墙高级设置

1. 按 `Win + R`，输入 `wf.msc`，按回车
2. 或者：控制面板 → 系统和安全 → Windows Defender 防火墙 → 高级设置

#### 步骤 2：创建入站规则

1. 在左侧选择 **"入站规则"**
2. 在右侧点击 **"新建规则..."**
3. 选择规则类型：
   - 选择 **"端口"**
   - 点击 **"下一步"**
4. 协议和端口：
   - 选择 **"TCP"**
   - 选择 **"特定本地端口"**
   - 输入端口号：**`5000`**
   - 点击 **"下一步"**
5. 操作：
   - 选择 **"允许连接"**
   - 点击 **"下一步"**
6. 配置文件：
   - 勾选所有三个选项：
     - ✅ **域**
     - ✅ **专用**
     - ✅ **公用**
   - 点击 **"下一步"**
7. 名称：
   - 名称：**`Flask App Port 5000`**
   - 描述：**`允许 Flask 应用在端口 5000 上接收连接`**
   - 点击 **"完成"**

#### 步骤 3：验证规则

1. 在 **"入站规则"** 列表中，找到 **"Flask App Port 5000"**
2. 确认规则状态为 **"已启用"**（绿色对勾）
3. 如果未启用，右键点击规则 → **"启用规则"**

### 方法 3：使用命令行（CMD/PowerShell）

#### 以管理员身份运行 PowerShell 或 CMD

```powershell
# 添加防火墙规则（允许端口 5000 的 TCP 入站连接）
netsh advfirewall firewall add rule name="Flask App Port 5000" dir=in action=allow protocol=TCP localport=5000

# 或者使用 PowerShell 命令
New-NetFirewallRule -DisplayName "Flask App Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

#### 验证规则已添加

```powershell
# 查看规则
netsh advfirewall firewall show rule name="Flask App Port 5000"

# 或使用 PowerShell
Get-NetFirewallRule -DisplayName "Flask App Port 5000"
```

### 方法 4：临时禁用防火墙（仅用于测试）

⚠️ **警告**：仅用于测试，生产环境不推荐！

```powershell
# 临时禁用防火墙（不推荐用于生产环境）
netsh advfirewall set allprofiles state off

# 重新启用防火墙
netsh advfirewall set allprofiles state on
```

## 验证配置

### 1. 检查防火墙规则

```powershell
# 查看所有端口 5000 相关的规则
Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*5000*" -or $_.DisplayName -like "*Flask*"} | Format-Table DisplayName, Enabled, Direction, Action
```

### 2. 测试端口是否开放

在**本地电脑**上，使用 PowerShell 测试：

```powershell
# 测试端口是否可达
Test-NetConnection -ComputerName 10.78.44.3 -Port 5000

# 或使用 telnet（需要启用 telnet 客户端）
telnet 10.78.44.3 5000
```

### 3. 测试 HTTP 请求

在**本地电脑**上，使用 PowerShell 测试：

```powershell
# 测试 GET 请求
Invoke-WebRequest -Uri "http://10.78.44.3:5000/" -Method GET

# 测试 PUT 请求
Invoke-WebRequest -Uri "http://10.78.44.3:5000/api/admin/users/8" -Method PUT -Headers @{"Content-Type"="application/json"} -Body '{"test":"data"}'
```

## 常见问题

### Q1: 规则已添加，但仍然无法连接？

**可能原因：**
1. 规则未应用到所有配置文件（域/专用/公用）
2. 有其他防火墙规则阻止了连接
3. 网络中间设备（路由器、交换机）阻止了连接

**解决方法：**
1. 检查规则是否应用到所有配置文件
2. 检查是否有其他阻止规则优先级更高
3. 检查网络设备配置

### Q2: 如何查看防火墙日志？

```powershell
# 启用防火墙日志记录
netsh advfirewall set allprofiles logging filename %windir%\system32\LogFiles\Firewall\pfirewall.log
netsh advfirewall set allprofiles logging maxfilesize 4096
netsh advfirewall set allprofiles logging droppedconnections enable
netsh advfirewall set allprofiles logging allowedconnections enable

# 查看日志位置
notepad %windir%\system32\LogFiles\Firewall\pfirewall.log
```

### Q3: 如何删除防火墙规则？

```powershell
# 删除规则
netsh advfirewall firewall delete rule name="Flask App Port 5000"

# 或使用 PowerShell
Remove-NetFirewallRule -DisplayName "Flask App Port 5000"
```

### Q4: 服务器有多个网卡，如何指定？

```powershell
# 为特定网卡添加规则
New-NetFirewallRule -DisplayName "Flask App Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -InterfaceAlias "以太网"
```

## 生产环境建议

1. **不要禁用防火墙**：只添加必要的规则
2. **限制源 IP**（如果可能）：
   ```powershell
   # 只允许特定 IP 访问（可选）
   New-NetFirewallRule -DisplayName "Flask App Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -RemoteAddress 10.78.35.252
   ```
3. **使用 HTTPS**：配置 SSL/TLS 加密
4. **使用反向代理**：使用 nginx 等反向代理，只开放 80/443 端口
5. **定期审查规则**：删除不再需要的规则

## 相关文件

- `check_firewall.ps1` - 检查防火墙规则脚本
- `add_firewall_rule.ps1` - 添加防火墙规则脚本

## 联系支持

如果以上方法都无法解决问题，请检查：
1. 服务器网络配置
2. 路由器/交换机配置
3. 公司网络策略
4. 服务器日志文件 `logs/app.log`

