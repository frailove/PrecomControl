# 生产环境部署指南

> 目标：将 PrecomControl 系统部署到服务器，支撑 50-80 个并发用户。

## 1. 环境准备

| 组件 | 要求 | 说明 |
|------|------|------|
| 操作系统 | CentOS 7+/Ubuntu 20.04+/Windows Server 2019+ | Linux 更推荐 |
| Python | 3.8 及以上 | 建议使用官方发行版 |
| MySQL | 5.7+/8.0+ | 需调高 `max_connections` ≥150（注意：这是 MySQL 服务器最大连接数，不是连接池大小） |
| 网络 | 放行 5000 端口（或 HTTP/HTTPS 端口） | 可配合 Nginx 反向代理 |

### 1.1 创建部署目录

```bash
# Linux
sudo mkdir -p /opt/precomcontrol && cd /opt/precomcontrol

# Windows
md C:\PrecomControl && cd C:\PrecomControl
```

### 1.2 同步代码

- **直接复制**：将本地整个项目目录（含 `app.py`、`routes/`、`templates/`、`static/` 等）上传到服务器
- **Git 方式**：
  ```bash
  git clone <your_repo_url> /opt/precomcontrol
  ```

### 1.3 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate          # Linux
venv\Scripts\activate             # Windows
pip install -r requirements.txt   # 如果文件缺失，可在本地重新生成
```

> 若没有 `requirements.txt`，可在开发机执行 `pip freeze > requirements.txt` 后一并上传。

## 2. 数据库准备

1. 确保 MySQL 中已创建 `PRECOMCONTROL` 数据库，并配置账号密码（生产环境建议修改默认 `DB_CONFIG`）  
2. 调整 MySQL 配置（示例）：
   ```ini
   [mysqld]
   max_connections = 200
   wait_timeout = 600
   interactive_timeout = 600
   ```
3. 启动程序时会自动建表，无需手工执行 SQL

## 3. 配置环境变量

在服务器上设置以下变量（可写入 `.env`、systemd unit、或系统环境变量）：

```bash
export FLASK_SECRET_KEY='生产环境随机Key'
export FLASK_DEBUG=False
export FLASK_HTTPS=True                 # 若使用 HTTPS
export DB_HOST=10.78.44.17              # 如需覆盖默认配置
export DB_USER=xxx
export DB_PASSWORD=yyy
```

> Windows 可使用 `set VAR=value`（临时）或“系统变量”面板设置。

## 4. 启动方式

### 4.1 推荐（Linux）：Gunicorn + Nginx

```bash
bash start_production.sh
```

脚本等价于：

```bash
source venv/bin/activate
mkdir -p logs
gunicorn -c gunicorn_config.py wsgi:app
```

#### 使用 systemd 守护（可选）

```ini
# /etc/systemd/system/precom.service
[Unit]
Description=PrecomControl
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/precomcontrol
Environment="FLASK_SECRET_KEY=xxxx"
ExecStart=/opt/precomcontrol/venv/bin/gunicorn -c gunicorn_config.py wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now precom.service
```

### 4.2 Windows：Waitress

```bash
python start_production.bat
```

手动方式：

```bash
venv\Scripts\activate
mkdir logs
waitress-serve --listen=0.0.0.0:5000 --threads=8 wsgi:app
```

> 若需后台服务，可使用 NSSM、任务计划程序等工具。

### 4.3 配置 Nginx + HTTPS

为避免暴露 IP、提供固定域名入口，建议使用 Nginx 反向代理 + Let’s Encrypt 证书。

1. **准备域名**：在 DNS 控制台添加 A 记录，将 `cc7projectcontrols.com` 指到服务器公网 IP（主机记录填 `@` 或留空）。
2. **安装 Nginx + Certbot**
   ```bash
   sudo apt install nginx certbot python3-certbot-nginx
   ```
3. **导入配置**
   ```bash
   sudo cp nginx/precomcontrol.conf /etc/nginx/sites-available/precomcontrol
   sudo ln -s /etc/nginx/sites-available/precomcontrol /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
   - 配置中包含 HTTP → HTTPS 重定向、静态资源缓存、健康检查等。
4. **申请 HTTPS 证书**
   ```bash
   sudo certbot --nginx -d cc7projectcontrols.com
   ```
   - Certbot 会自动续期证书。若暂时只需 HTTP，可先不执行此步。
5. **或使用脚本**
   ```bash
   sudo bash setup_nginx.sh
   ```
   - 按提示输入域名、项目路径，一次性完成安装与证书配置。

> 如果只是内部局域网使用，也可以通过 hosts 文件临时映射域名到服务器 IP，但正式环境建议走 DNS + Nginx。

### 4.4 开发调试模式（仅本地）

```bash
python app.py
```

> 内置 Flask 服务器仅用于调试，请勿用于生产环境。

## 5. Nginx 反向代理（可选）

```nginx
server {
    listen 80;
    server_name precom.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> 开启 HTTPS：将 `listen 80` 改为 `listen 443 ssl;` 并配置证书（Let’s Encrypt 等）。

## 6. 性能与监控

- **数据库连接池**：`database.py` 中默认 `pool_size=100`，可按需调整
- **Gunicorn 配置**：
  - workers：CPU 核心数 * 2 + 1（默认自动计算）
  - timeout：120 秒
  - max_requests：1000（防止内存泄漏）
- **健康检查**：`curl http://server:5000/health`
- **日志文件**：
  - 应用：`logs/app.log`
  - Gunicorn：`logs/gunicorn_access.log` / `logs/gunicorn_error.log`
- **数据库连接数**：`SHOW STATUS LIKE 'Threads_connected';`

## 7. 常见问题排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 500 错误 | 依赖或环境变量缺失 | 查看 `logs/app.log`，确认 venv 是否激活 |
| 连接池耗尽 | 并发过高 | 调整 MySQL `max_connections` 或 `pool_size` |
| 静态资源无法加载 | 未配置 Nginx static | 确认 `STATIC_URL_PATH` 或 Nginx 配置 |
| 性能不足 | Gunicorn worker 数量不够 | 调整 `workers`、`worker_class`、`keepalive` |
| HTTPS 警告 | 自签名证书 | 使用可信 CA 证书 |

## 8. 安全建议

1. 强制 HTTPS，限制来源 IP
2. 使用最小权限的数据库账号
3. 启用 WAF/Fail2Ban 防暴力破解
4. 定期备份数据库及日志
5. 防火墙仅开放必要端口（80/443/22/3306）

## 9. 验收清单

- [ ] `/health` 返回 `status=healthy`
- [ ] 登录/登出、系统/子系统/试压包等核心页面正常
- [ ] 上传/导入 Excel 正常
- [ ] 日志目录有最新记录
- [ ] Nginx/反向代理策略生效

完成以上步骤后，即可对外提供稳定的测试/生产服务。如遇问题，可根据“常见问题”逐项排查或查看 `logs/` 下的日志文件。***
