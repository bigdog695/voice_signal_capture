@echo off
echo 正在安装Python后端依赖...
cd /d "%~dp0"
pip install -r requirements.txt
echo 依赖安装完成！
echo.
echo 启动服务器...
python main.py
pause
