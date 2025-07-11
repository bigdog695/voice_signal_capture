@echo off
echo 启动Voice Chat Backend服务器（带ASR功能）...
echo.
echo 检查并安装依赖...
cd /d "%~dp0"

REM 检查虚拟环境是否存在
if exist "venv\Scripts\activate.bat" (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    echo 使用全局环境安装依赖...
    pip install -r requirements.txt
)

echo 依赖安装完成！
echo.
echo 服务信息:
echo - API文档: http://localhost:8000/docs
echo - 健康检查: http://localhost:8000/health
echo - ASR信息: http://localhost:8000/asr/info
echo - WebSocket Chat: ws://localhost:8000/chatting?id=chat_id
echo - WebSocket ASR: ws://localhost:8000/ws
echo.
echo 启动服务器...
python main.py
pause
