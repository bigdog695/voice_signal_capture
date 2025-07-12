@echo off
echo ========================================
echo Voice Chat Backend Docker 部署脚本
echo ========================================
echo.

cd /d "%~dp0"

echo 检查Docker是否运行...
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker未安装或未启动
    echo 请先安装并启动Docker Desktop
    pause
    exit /b 1
)

echo Docker检查通过
echo.

:menu
echo 请选择操作:
echo 1. 构建Docker镜像
echo 2. 启动服务 (Docker Compose)
echo 3. 停止服务
echo 4. 查看日志
echo 5. 重建并启动
echo 6. 清理容器和镜像
echo 0. 退出
echo.
set /p choice=请输入选择 (0-6): 

if "%choice%"=="1" goto build
if "%choice%"=="2" goto start
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto rebuild
if "%choice%"=="6" goto cleanup
if "%choice%"=="0" goto exit
echo 无效选择，请重试
goto menu

:build
echo.
echo 构建Docker镜像...
docker build -t voice-chat-backend .
if errorlevel 1 (
    echo 构建失败
    pause
    goto menu
)
echo 构建完成
goto menu

:start
echo.
echo 启动服务...
docker-compose up -d
if errorlevel 1 (
    echo 启动失败
    pause
    goto menu
)
echo.
echo 服务已启动！
echo - API文档: http://localhost:8000/docs
echo - 健康检查: http://localhost:8000/health
echo - ASR信息: http://localhost:8000/asr/info
goto menu

:stop
echo.
echo 停止服务...
docker-compose down
echo 服务已停止
goto menu

:logs
echo.
echo 查看实时日志 (按 Ctrl+C 退出):
docker-compose logs -f
goto menu

:rebuild
echo.
echo 重建并启动服务...
docker-compose down
docker build -t voice-chat-backend .
docker-compose up -d
echo.
echo 服务已重新启动！
echo - API文档: http://localhost:8000/docs
echo - 健康检查: http://localhost:8000/health
echo - ASR信息: http://localhost:8000/asr/info
goto menu

:cleanup
echo.
echo 清理容器和镜像...
docker-compose down --rmi all --volumes --remove-orphans
echo 清理完成
goto menu

:exit
echo 退出脚本
exit /b 0
