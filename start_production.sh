#!/bin/bash
# 生产环境启动脚本（Linux）
# 使用 Gunicorn WSGI 服务器

echo "========================================"
echo "预试车管理系统 - 生产环境启动"
echo "========================================"

# 创建日志目录
mkdir -p logs

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3环境"
    exit 1
fi

# 检查Gunicorn
if ! python3 -c "import gunicorn" 2>/dev/null; then
    echo "安装 Gunicorn WSGI 服务器..."
    pip3 install gunicorn
fi

# 启动应用
echo ""
echo "启动应用服务器..."
echo "访问地址: http://0.0.0.0:5000"
echo "按 Ctrl+C 停止服务器"
echo ""

# 使用Gunicorn启动
gunicorn -c gunicorn_config.py wsgi:app

