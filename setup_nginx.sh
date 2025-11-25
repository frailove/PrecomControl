#!/bin/bash
# Nginx 反向代理配置脚本
# 用于配置域名和 HTTPS

set -e

echo "=========================================="
echo "PrecomControl Nginx 配置脚本"
echo "=========================================="
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo "错误: 请使用 sudo 运行此脚本"
    exit 1
fi

# 获取域名
read -p "请输入你的域名（例如: cc7projectcontrols.com）: " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo "错误: 域名不能为空"
    exit 1
fi

# 获取项目路径
read -p "请输入项目路径（默认: /opt/precomcontrol）: " PROJECT_PATH
PROJECT_PATH=${PROJECT_PATH:-/opt/precomcontrol}

echo ""
echo "配置信息:"
echo "  域名: $DOMAIN"
echo "  项目路径: $PROJECT_PATH"
echo ""
read -p "确认继续? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "已取消"
    exit 0
fi

# 1. 安装 Nginx（如果未安装）
if ! command -v nginx &> /dev/null; then
    echo "安装 Nginx..."
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y nginx
    elif command -v yum &> /dev/null; then
        yum install -y nginx
    else
        echo "错误: 无法自动安装 Nginx，请手动安装"
        exit 1
    fi
fi

# 2. 安装 Certbot（Let's Encrypt 客户端）
if ! command -v certbot &> /dev/null; then
    echo "安装 Certbot..."
    if command -v apt-get &> /dev/null; then
        apt-get install -y certbot python3-certbot-nginx
    elif command -v yum &> /dev/null; then
        yum install -y certbot python3-certbot-nginx
    else
        echo "警告: 无法自动安装 Certbot，请手动安装"
    fi
fi

# 3. 创建 Nginx 配置文件
echo "创建 Nginx 配置文件..."
NGINX_CONFIG="/etc/nginx/sites-available/precomcontrol"
cat > "$NGINX_CONFIG" <<EOF
# PrecomControl Nginx 反向代理配置

# HTTP 重定向到 HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    # Let's Encrypt 证书验证
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # 其他所有请求重定向到 HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS 配置
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;

    # SSL 证书配置（Let's Encrypt）
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 日志
    access_log /var/log/nginx/precomcontrol_access.log;
    error_log /var/log/nginx/precomcontrol_error.log;

    # 客户端上传大小限制
    client_max_body_size 500M;
    client_body_timeout 300s;

    # 反向代理到 Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$server_name;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # 静态文件
    location /static/ {
        alias $PROJECT_PATH/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:5000/health;
        access_log off;
    }
}
EOF

# 4. 创建软链接
echo "启用 Nginx 配置..."
ln -sf "$NGINX_CONFIG" /etc/nginx/sites-enabled/precomcontrol

# 5. 测试 Nginx 配置
echo "测试 Nginx 配置..."
nginx -t

# 6. 获取 SSL 证书
echo ""
echo "=========================================="
echo "获取 Let's Encrypt SSL 证书"
echo "=========================================="
echo ""
echo "请确保："
echo "  1. 域名 $DOMAIN 已解析到此服务器的 IP 地址"
echo "  2. 防火墙已开放 80 和 443 端口"
echo ""
read -p "域名已解析完成? (y/n): " DNS_READY

if [ "$DNS_READY" = "y" ]; then
    echo "获取 SSL 证书..."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@$DOMAIN --redirect
    
    if [ $? -eq 0 ]; then
        echo "✅ SSL 证书获取成功！"
    else
        echo "⚠️  SSL 证书获取失败，请检查域名解析和网络连接"
        echo "可以稍后手动运行: certbot --nginx -d $DOMAIN"
    fi
else
    echo "⚠️  跳过 SSL 证书获取"
    echo "域名解析完成后，请运行: certbot --nginx -d $DOMAIN"
fi

# 7. 重启 Nginx
echo "重启 Nginx..."
systemctl restart nginx
systemctl enable nginx

echo ""
echo "=========================================="
echo "✅ Nginx 配置完成！"
echo "=========================================="
echo ""
echo "访问地址:"
echo "  HTTP:  http://$DOMAIN (自动重定向到 HTTPS)"
echo "  HTTPS: https://$DOMAIN"
echo ""
echo "注意事项:"
echo "  1. 确保 Gunicorn 在 127.0.0.1:5000 运行"
echo "  2. 确保防火墙开放 80 和 443 端口"
echo "  3. SSL 证书会自动续期（certbot 定时任务）"
echo ""

