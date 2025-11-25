@echo off
chcp 65001 >nul
echo ====================================
echo Windows Nginx 配置向导
echo ====================================
echo.
echo 此脚本将帮助您配置 Nginx for Windows
echo 域名: cc7projectcontrols.com
echo.

set /p PROJECT_PATH="请输入项目路径 [C:\Projects\PrecomControl]: "
if "%PROJECT_PATH%"=="" set PROJECT_PATH=C:\Projects\PrecomControl

set /p NGINX_PATH="请输入 Nginx 安装路径 [C:\nginx]: "
if "%NGINX_PATH%"=="" set NGINX_PATH=C:\nginx

echo.
echo ====================================
echo 步骤 1: 检查 Nginx 是否已安装
echo ====================================
if not exist "%NGINX_PATH%\nginx.exe" (
    echo [错误] Nginx 未在 %NGINX_PATH% 找到
    echo.
    echo 请先下载并解压 Nginx:
    echo 1. 访问: https://nginx.org/en/download.html
    echo 2. 下载 Windows 版本
    echo 3. 解压到 %NGINX_PATH%
    echo.
    pause
    exit /b 1
)
echo [✓] Nginx 已找到

echo.
echo ====================================
echo 步骤 2: 复制配置文件
echo ====================================
if not exist "%NGINX_PATH%\conf\precomcontrol.conf" (
    copy "%~dp0nginx\precomcontrol.conf" "%NGINX_PATH%\conf\precomcontrol.conf"
    echo [✓] 配置文件已复制
) else (
    echo [提示] 配置文件已存在，跳过复制
)

echo.
echo ====================================
echo 步骤 3: 修改配置文件路径
echo ====================================
powershell -Command "(Get-Content '%NGINX_PATH%\conf\precomcontrol.conf') -replace '/opt/precomcontrol/static/', '%PROJECT_PATH:\=/%/static/' | Set-Content '%NGINX_PATH%\conf\precomcontrol.conf'"
powershell -Command "(Get-Content '%NGINX_PATH%\conf\precomcontrol.conf') -replace '/etc/letsencrypt/live/cc7projectcontrols.com', 'C:/nginx/conf/ssl/cc7projectcontrols.com' | Set-Content '%NGINX_PATH%\conf\precomcontrol.conf'"
echo [✓] 路径已更新

echo.
echo ====================================
echo 步骤 4: 更新 nginx.conf
echo ====================================
findstr /C:"include precomcontrol.conf" "%NGINX_PATH%\conf\nginx.conf" >nul
if errorlevel 1 (
    echo. >> "%NGINX_PATH%\conf\nginx.conf"
    echo     include precomcontrol.conf; >> "%NGINX_PATH%\conf\nginx.conf"
    echo [✓] nginx.conf 已更新
) else (
    echo [提示] nginx.conf 已包含配置，跳过
)

echo.
echo ====================================
echo 步骤 5: 测试 Nginx 配置
echo ====================================
cd /d "%NGINX_PATH%"
nginx.exe -t
if errorlevel 1 (
    echo [错误] Nginx 配置测试失败，请检查配置文件
    pause
    exit /b 1
)
echo [✓] 配置测试通过

echo.
echo ====================================
echo 步骤 6: 创建 SSL 证书目录
echo ====================================
if not exist "%NGINX_PATH%\conf\ssl" mkdir "%NGINX_PATH%\conf\ssl"
echo [✓] SSL 目录已创建

echo.
echo ====================================
echo 配置完成！
echo ====================================
echo.
echo 下一步操作：
echo.
echo 1. 配置 DNS 解析：
echo    - 登录域名管理后台
echo    - 添加 A 记录: @ (或留空) -> 你的服务器IP
echo    - 等待 10-30 分钟生效
echo.
echo 2. 获取 SSL 证书（使用 win-acme）：
echo    - 下载: https://www.win-acme.com/
echo    - 运行: wacs.exe
echo    - 选择: N (新证书) -> 2 (手动输入) -> cc7projectcontrols.com
echo    - 验证方式: 1 (HTTP文件验证)
echo    - 存储方式: 2 (Nginx)
echo    - 证书路径: %NGINX_PATH%\conf\ssl\
echo.
echo 3. 启动 Nginx：
echo    cd %NGINX_PATH%
echo    nginx.exe
echo.
echo 4. 测试访问：
echo    https://cc7projectcontrols.com
echo.
pause

