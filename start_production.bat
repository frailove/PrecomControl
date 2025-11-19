@echo off
REM 生产环境启动脚本（Windows）
REM 使用 Waitress WSGI 服务器

echo ========================================
echo 预试车管理系统 - 生产环境启动
echo ========================================

REM 创建日志目录
if not exist logs mkdir logs

REM 检查Python环境
python --version
if errorlevel 1 (
    echo 错误: 未找到Python环境
    pause
    exit /b 1
)

REM 安装依赖（如果需要）
echo 检查依赖...
pip show waitress >nul 2>&1
if errorlevel 1 (
    echo 安装 Waitress WSGI 服务器...
    pip install waitress
)

REM 启动应用
echo.
echo 启动应用服务器...
echo 访问地址: http://0.0.0.0:5000
echo 按 Ctrl+C 停止服务器
echo.

python -m waitress --listen=0.0.0.0:5000 --threads=8 wsgi:app

pause

