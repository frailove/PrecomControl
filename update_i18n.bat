@echo off
echo ====================================
echo 更新翻译文件
echo ====================================

REM 1. 提取最新的翻译文本
echo [1/2] 提取最新翻译文本...
pybabel extract -F babel.cfg -k _l -o messages.pot .

REM 2. 更新现有翻译文件
echo [2/2] 更新翻译文件...
pybabel update -i messages.pot -d translations

echo.
echo ====================================
echo 更新完成！
echo ====================================
echo.
echo 下一步：
echo 1. 编辑更新后的 .po 文件
echo 2. 运行 compile_i18n.bat 编译
echo.
pause

