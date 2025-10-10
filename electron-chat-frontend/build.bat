necho 完成。
@echo off
REM Windows build wrapper for 12345智能助手 - calls PowerShell build script (pwsh or powershell)
setlocal enabledelayedexpansion

echo =====================================
echo   12345智能助手 - Windows 构建包装脚本
echo =====================================

:: Resolve script directory (handles spaces)
set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%" >nul 2>&1

:: Check for Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装: https://nodejs.org/
    echo 如果已安装但命令未找到, 请重新打开终端或加入 PATH。
    goto :end_fail
)
for /f "delims=" %%v in ('node -v') do set NODE_VERSION=%%v
echo [信息] 检测到 Node.js 版本 %NODE_VERSION%

:: Choose PowerShell executable (prefer pwsh)
set POWERSHELL_CMD=
where pwsh >nul 2>&1 && set POWERSHELL_CMD=pwsh
if not defined POWERSHELL_CMD (
    where powershell >nul 2>&1 && set POWERSHELL_CMD=powershell
)
if not defined POWERSHELL_CMD (
    echo [错误] 未找到 PowerShell (pwsh 或 powershell)。
    goto :end_fail
)
echo [信息] 使用 PowerShell: %POWERSHELL_CMD%

:: Ensure dependencies
if not exist "%SCRIPT_DIR%node_modules" (
    echo [步骤] 安装依赖 (npm install)...
    call npm install
    if errorlevel 1 (
        echo [错误] npm install 失败
        goto :end_fail
    )
) else (
    echo [跳过] 已存在 node_modules, 不重新安装。如需强制请删除该目录。
)

:: Run build script (pass arguments)
echo [步骤] 调用 PowerShell 构建脚本 build.ps1 (%*)
%POWERSHELL_CMD% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build.ps1" %*
if errorlevel 1 (
    echo [错误] 构建脚本执行失败
    goto :end_fail
)

:: Open output if exists
if exist "%SCRIPT_DIR%dist" (
    echo [成功] 构建完成，输出目录: %SCRIPT_DIR%dist
    for %%f in ("%SCRIPT_DIR%dist\AI*Setup*.exe") do (
        if exist "%%~f" echo [产物] 安装包: %%~nxf
    )
    start "" "%SCRIPT_DIR%dist"
) else (
    echo [警告] 未找到 dist 目录。
)

goto :end_ok

:end_fail
echo.
echo ==== 构建未成功完成 ====
set EXIT_CODE=1
goto :final

:end_ok
echo.
echo ==== 构建流程完成 ====
set EXIT_CODE=0

:final
popd >nul 2>&1
echo 按任意键退出...
pause >nul
exit /b %EXIT_CODE%
