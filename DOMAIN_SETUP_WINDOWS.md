# Windows 服务器域名配置指南

> 将购买的域名 `cc7projectcontrols.com` 配置到 Windows 服务器，实现 HTTPS 访问

## 📋 前置条件

- ✅ 已购买域名：`cc7projectcontrols.com`
- ✅ Windows 服务器已运行 PrecomControl 应用（端口 5000）
- ✅ 服务器有公网 IP 地址
- ✅ 防火墙已开放 80 和 443 端口

---

## 🔧 第一步：域名 DNS 解析

### 1.1 登录域名管理后台

登录你购买域名的服务商后台（如阿里云、腾讯云、GoDaddy 等），找到 **DNS 解析** 或 **域名解析** 功能。

### 1.2 添加 A 记录

添加一条 **A 记录**：

| 记录类型 | 主机记录 | 记录值 | TTL |
|---------|---------|--------|-----|
| A | @ (或留空) | 你的服务器公网IP | 600（或默认） |

**说明**：
- **主机记录**：`@` 或留空（表示根域名 `cc7projectcontrols.com`）
- **记录值**：填写你的 Windows 服务器的**公网 IP 地址**
- **TTL**：600 秒（10分钟）或使用默认值

### 1.3 验证解析

等待 5-10 分钟后，在本地电脑执行：

```powershell
# PowerShell
nslookup cc7projectcontrols.com

# 或 CMD
ping cc7projectcontrols.com
```

应该能看到返回你的服务器 IP 地址。

---

## 🚀 第二步：选择反向代理方案

Windows 上有两种方案，**推荐方案 A（Nginx）**，更简单。

### 方案 A：Nginx for Windows（推荐）

#### 2.1 下载 Nginx

1. 访问：https://nginx.org/en/download.html
2. 下载 **Windows 版本**（如 `nginx/Windows-1.24.0`）
3. 解压到 `C:\nginx`（或任意目录）

#### 2.2 配置 Nginx

1. **复制配置文件**：
   ```powershell
   # 将项目中的 nginx/precomcontrol.conf 复制到 C:\nginx\conf\precomcontrol.conf
   ```

2. **修改配置文件**：
   编辑 `C:\nginx\conf\precomcontrol.conf`，将路径改为 Windows 格式：
   ```nginx
   # 静态文件路径（改为你的项目路径）
   location /static/ {
       alias C:/Projects/PrecomControl/static/;
       expires 30d;
       add_header Cache-Control "public, immutable";
       access_log off;
   }
   ```

3. **修改主配置文件**：
   编辑 `C:\nginx\conf\nginx.conf`，在 `http { }` 块中添加：
   ```nginx
   http {
       # ... 其他配置 ...
       
       include precomcontrol.conf;  # 添加这一行
   }
   ```

#### 2.3 获取 SSL 证书（win-acme）

1. **下载 win-acme**：
   - 访问：https://www.win-acme.com/
   - 下载最新版本，解压到 `C:\win-acme`

2. **运行 win-acme**：
   ```powershell
   cd C:\win-acme
   .\wacs.exe
   ```

3. **按提示操作**：
   - 选择 `N`（创建新证书）
   - 选择 `2`（手动输入域名）
   - 输入域名：`cc7projectcontrols.com`
   - 选择验证方式：`1`（HTTP 文件验证）
   - 选择存储方式：`1`（IIS 站点）或 `2`（Nginx）
   - 如果选择 Nginx，会提示输入证书保存路径，填写：`C:\nginx\conf\ssl\`

4. **证书自动续期**：
   win-acme 会自动创建 Windows 计划任务，证书到期前自动续期。

#### 2.4 更新 Nginx 配置中的证书路径

编辑 `C:\nginx\conf\precomcontrol.conf`，修改证书路径：
```nginx
ssl_certificate C:/nginx/conf/ssl/cc7projectcontrols.com/fullchain.pem;
ssl_certificate_key C:/nginx/conf/ssl/cc7projectcontrols.com/privkey.pem;
```

#### 2.5 启动 Nginx

```powershell
cd C:\nginx
.\nginx.exe

# 测试配置
.\nginx.exe -t

# 重新加载配置（修改后）
.\nginx.exe -s reload
```

#### 2.6 设置 Nginx 为 Windows 服务（可选）

使用 [NSSM](https://nssm.cc/) 将 Nginx 注册为 Windows 服务：

```powershell
# 下载 NSSM，解压后运行
.\nssm.exe install Nginx "C:\nginx\nginx.exe"
.\nssm.exe set Nginx AppDirectory "C:\nginx"
```

---

### 方案 B：IIS 反向代理

如果你更熟悉 IIS，可以使用 IIS 作为反向代理。

#### 2.1 安装 IIS 和 ARR 模块

1. **启用 IIS**：
   - 控制面板 → 程序 → 启用或关闭 Windows 功能
   - 勾选：`Internet Information Services` 及其子项

2. **安装 URL Rewrite 和 ARR**：
   - URL Rewrite：https://www.iis.net/downloads/microsoft/url-rewrite
   - Application Request Routing：https://www.iis.net/downloads/microsoft/application-request-routing

#### 2.2 配置 IIS 站点

1. **创建新站点**：
   - 打开 IIS 管理器
   - 右键「网站」→「添加网站」
   - 网站名称：`PrecomControl`
   - 物理路径：`C:\Projects\PrecomControl\static`（临时，用于证书验证）
   - 绑定：HTTP，主机名 `cc7projectcontrols.com`，端口 80

2. **获取 SSL 证书**：
   - 使用 win-acme（同上），选择 `1`（IIS 站点）
   - win-acme 会自动配置 IIS 绑定

3. **配置反向代理**：
   - 在 IIS 管理器中，选择 `PrecomControl` 站点
   - 双击「URL 重写」
   - 添加规则 →「反向代理」
   - 输入规则：`(.*)`
   - 重写 URL：`http://127.0.0.1:5000/{R:1}`
   - 勾选「启用 SSL 卸载」

4. **配置 ARR**：
   - 在服务器级别，打开「Application Request Routing」
   - 点击「服务器代理设置」
   - 勾选「启用代理」

---

## ✅ 第三步：验证配置

### 3.1 测试 HTTP 重定向

访问：`http://cc7projectcontrols.com`

应该自动跳转到：`https://cc7projectcontrols.com`

### 3.2 测试 HTTPS

访问：`https://cc7projectcontrols.com`

- ✅ 浏览器地址栏显示 🔒 锁图标
- ✅ 能正常访问应用首页
- ✅ 不再显示 IP 地址

### 3.3 检查日志

**Nginx 日志**：
```powershell
# 访问日志
Get-Content C:\nginx\logs\precomcontrol_access.log -Tail 20

# 错误日志
Get-Content C:\nginx\logs\precomcontrol_error.log -Tail 20
```

**应用日志**：
```powershell
Get-Content C:\Projects\PrecomControl\logs\app.log -Tail 20
```

---

## 🔒 第四步：安全加固

### 4.1 防火墙规则

确保 Windows 防火墙允许：
- **入站规则**：端口 80（HTTP）、443（HTTPS）
- **出站规则**：端口 5000（本地，Nginx → Flask）

### 4.2 更新 Flask 配置

确保 `config.py` 中：
```python
SESSION_COOKIE_SECURE = True  # HTTPS 下必须为 True
```

### 4.3 证书自动续期

win-acme 会自动续期，但建议：
- 定期检查计划任务是否正常运行
- 证书到期前 30 天会收到邮件提醒（如果配置了）

---

## 🐛 常见问题

### Q1: DNS 解析不生效？

**检查**：
1. DNS 记录是否正确（A 记录，主机名 `precom`，值是你的 IP）
2. 等待时间是否足够（最长 48 小时，通常 10-30 分钟）
3. 本地 DNS 缓存：`ipconfig /flushdns`

### Q2: 证书申请失败？

**可能原因**：
1. 域名解析未生效（先验证 DNS）
2. 80 端口被占用（Nginx/IIS 需要监听 80 端口用于验证）
3. 防火墙阻止了 80 端口

**解决**：
```powershell
# 检查端口占用
netstat -ano | findstr :80

# 检查防火墙
netsh advfirewall firewall show rule name=all | findstr "80\|443"
```

### Q3: Nginx 启动失败？

**检查**：
```powershell
# 测试配置
cd C:\nginx
.\nginx.exe -t

# 查看错误日志
Get-Content C:\nginx\logs\error.log
```

### Q4: 访问显示 502 Bad Gateway？

**原因**：Nginx 无法连接到 Flask 应用（端口 5000）

**解决**：
1. 确认 Flask 应用正在运行：`netstat -ano | findstr :5000`
2. 检查 Nginx 配置中的 `proxy_pass` 地址是否正确
3. 检查 Windows 防火墙是否阻止了本地连接

---

## 📝 快速检查清单

- [ ] DNS 解析已配置（A 记录指向服务器 IP）
- [ ] DNS 解析已生效（`nslookup cc7projectcontrols.com` 返回正确 IP）
- [ ] Nginx/IIS 已安装并运行
- [ ] SSL 证书已申请（win-acme）
- [ ] 防火墙已开放 80 和 443 端口
- [ ] Flask 应用正在运行（端口 5000）
- [ ] 可以访问 `https://cc7projectcontrols.com`
- [ ] 浏览器显示 🔒 锁图标（证书有效）

---

## 🎯 完成！

配置完成后，用户可以通过 `https://cc7projectcontrols.com` 访问你的应用，不再需要记住 IP 地址，也不会因为服务器重启导致端口变化而无法访问。

**下一步**：
- 将域名分享给团队成员
- 定期检查证书续期状态
- 监控 Nginx/IIS 日志，确保服务稳定运行

