@echo off
echo ================================
echo    12345智能助手 Frontend Setup
echo ================================
echo.

:: 检查Node.js是否安装
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未检测到Node.js，请先安装Node.js
    echo 下载地址: https://nodejs.org/
    pause
    exit /b 1
)

echo 检测到Node.js版本:
node --version
echo.

:: 检查是否已安装依赖
if not exist "node_modules" (
    echo 正在安装依赖包...
    call npm install
    if %errorlevel% neq 0 (
        echo 错误: 依赖安装失败
        pause
        exit /b 1
    )
    echo 依赖安装完成!
    echo.
)

echo 可用的命令:
echo 1. 运行Electron应用 (开发模式)
echo 2. 启动测试WebSocket服务器
echo 3. 同时启动应用和服务器
echo 4. 退出
echo.

set /p choice="请选择 (1-4): "

if "%choice%"=="1" (
    echo 正在启动Electron应用...
    call npm run dev
) else if "%choice%"=="2" (
    echo 正在启动WebSocket测试服务器...
    node websocket-server-example.js
) else if "%choice%"=="3" (
    echo 正在同时启动应用和服务器...
    start "WebSocket Server" cmd /k "node websocket-server-example.js"
    timeout /t 2 /nobreak >nul
    call npm run dev
) else if "%choice%"=="4" (
    exit /b 0
) else (
    echo 无效选择，请重新运行脚本
    pause
)

pause
