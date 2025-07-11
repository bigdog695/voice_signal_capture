@echo off
title Voice Chat Backend Docker 测试和部署

echo ============================================
echo Voice Chat Backend Docker 测试和部署工具
echo ============================================
echo.

cd /d "%~dp0"

REM 检查Docker是否运行
echo [1/6] 检查Docker服务状态...
docker info >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker Desktop未启动
    echo.
    echo 请执行以下步骤:
    echo 1. 启动Docker Desktop应用程序
    echo 2. 等待Docker完全启动（系统托盘图标不再转动）
    echo 3. 重新运行此脚本
    echo.
    echo 提示: 您可以从开始菜单搜索"Docker Desktop"来启动
    pause
    exit /b 1
)
echo √ Docker服务正常运行

echo.
echo [2/6] 显示项目信息...
echo 项目: Voice Chat Backend with FunASR
echo 镜像名: voice-chat-backend
echo 端口: 8000
echo ASR模型: paraformer-zh-streaming (v2.0.4)
echo.

echo [3/6] 构建Docker镜像...
echo 这可能需要几分钟时间，因为需要下载FunASR模型...
docker build -t voice-chat-backend .
if errorlevel 1 (
    echo 构建失败！请检查错误信息。
    pause
    exit /b 1
)
echo √ Docker镜像构建成功

echo.
echo [4/6] 停止现有容器（如果存在）...
docker stop voice-chat-backend-container 2>nul
docker rm voice-chat-backend-container 2>nul
echo √ 清理完成

echo.
echo [5/6] 启动容器...
docker run -d ^
    --name voice-chat-backend-container ^
    -p 8000:8000 ^
    --restart unless-stopped ^
    voice-chat-backend

if errorlevel 1 (
    echo 启动失败！
    pause
    exit /b 1
)
echo √ 容器启动成功

echo.
echo [6/6] 等待服务启动...
timeout /t 10 /nobreak > nul

echo.
echo ============================================
echo            部署完成！
echo ============================================
echo.
echo 服务信息:
echo - 容器名称: voice-chat-backend-container
echo - 访问地址: http://localhost:8000
echo - API文档: http://localhost:8000/docs
echo - 健康检查: http://localhost:8000/health
echo - ASR信息: http://localhost:8000/asr/info
echo.
echo WebSocket端点:
echo - 聊天: ws://localhost:8000/chatting?id=chat_active_001
echo - ASR: ws://localhost:8000/ws
echo.

echo [测试命令]
echo.
echo 1. 健康检查:
echo    curl http://localhost:8000/health
echo.
echo 2. ASR信息:
echo    curl http://localhost:8000/asr/info
echo.
echo 3. 查看日志:
echo    docker logs -f voice-chat-backend-container
echo.
echo 4. 停止服务:
echo    docker stop voice-chat-backend-container
echo.

:menu
echo 选择操作:
echo 1. 查看实时日志
echo 2. 测试健康检查
echo 3. 测试ASR信息
echo 4. 停止容器
echo 5. 重启容器
echo 0. 退出
echo.
set /p choice=请输入选择 (0-5): 

if "%choice%"=="1" goto logs
if "%choice%"=="2" goto health
if "%choice%"=="3" goto asr_info
if "%choice%"=="4" goto stop
if "%choice%"=="5" goto restart
if "%choice%"=="0" goto exit
echo 无效选择，请重试
goto menu

:logs
echo.
echo 查看实时日志 (按 Ctrl+C 退出):
docker logs -f voice-chat-backend-container
goto menu

:health
echo.
echo 测试健康检查:
curl -s http://localhost:8000/health
echo.
pause
goto menu

:asr_info
echo.
echo 测试ASR信息:
curl -s http://localhost:8000/asr/info
echo.
pause
goto menu

:stop
echo.
echo 停止容器...
docker stop voice-chat-backend-container
docker rm voice-chat-backend-container
echo 容器已停止并删除
pause
goto menu

:restart
echo.
echo 重启容器...
docker stop voice-chat-backend-container
docker rm voice-chat-backend-container
docker run -d ^
    --name voice-chat-backend-container ^
    -p 8000:8000 ^
    --restart unless-stopped ^
    voice-chat-backend
echo 容器已重启
goto menu

:exit
echo 退出测试工具
exit /b 0
