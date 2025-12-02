@echo off
echo ====================================
echo 初始化国际化支持
echo ====================================

REM 1. 安装Flask-Babel
echo [1/5] 安装Flask-Babel...
pip install Flask-Babel

REM 2. 创建translations目录
echo [2/5] 创建translations目录...
if not exist translations mkdir translations

REM 3. 提取需要翻译的文本
echo [3/5] 提取翻译文本...
pybabel extract -F babel.cfg -k _l -o messages.pot .

REM 4. 初始化英语翻译
echo [4/5] 初始化英语翻译...
pybabel init -i messages.pot -d translations -l en_US

REM 5. 初始化俄语翻译
echo [5/5] 初始化俄语翻译...
pybabel init -i messages.pot -d translations -l ru_RU

echo.
echo ====================================
echo 初始化完成！
echo ====================================
echo.
echo 下一步：
echo 1. 编辑 translations/en_US/LC_MESSAGES/messages.po
echo 2. 编辑 translations/ru_RU/LC_MESSAGES/messages.po
echo 3. 运行 compile_i18n.bat 编译翻译文件
echo.
pause

