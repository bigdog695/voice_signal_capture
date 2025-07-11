# AI Chat - 构建安装包 PowerShell脚本

param(
    [string]$BuildType = "ask"
)

Write-Host "================================" -ForegroundColor Cyan
Write-Host "    AI Chat - 构建安装包" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 检查Node.js
try {
    $nodeVersion = node --version
    Write-Host "检测到Node.js版本: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "错误: 未检测到Node.js，请先安装Node.js" -ForegroundColor Red
    Write-Host "下载地址: https://nodejs.org/" -ForegroundColor Yellow
    Read-Host "按Enter键退出"
    exit 1
}

# 检查package.json
if (-not (Test-Path "package.json")) {
    Write-Host "错误: 未找到package.json文件" -ForegroundColor Red
    Write-Host "请确保在项目根目录运行此脚本" -ForegroundColor Yellow
    Read-Host "按Enter键退出"
    exit 1
}

# 检查并安装依赖
Write-Host "正在检查依赖..." -ForegroundColor Yellow
if (-not (Test-Path "node_modules")) {
    Write-Host "正在安装依赖包..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: 依赖安装失败" -ForegroundColor Red
        Read-Host "按Enter键退出"
        exit 1
    }
}

# 清理之前的构建
Write-Host "正在清理之前的构建文件..." -ForegroundColor Yellow
if (Test-Path "dist") {
    Remove-Item -Path "dist" -Recurse -Force
}

# 选择构建类型
if ($BuildType -eq "ask") {
    Write-Host ""
    Write-Host "选择构建类型:" -ForegroundColor Cyan
    Write-Host "1. 仅打包 (便携版，无需安装)" -ForegroundColor White
    Write-Host "2. 制作安装包 (NSIS安装程序)" -ForegroundColor White
    Write-Host "3. 制作所有版本 (便携版 + 安装包)" -ForegroundColor White
    Write-Host "4. 退出" -ForegroundColor White
    Write-Host ""
    
    $choice = Read-Host "请选择构建类型 (1-4)"
} else {
    $choice = $BuildType
}

$buildTypeText = ""
switch ($choice) {
    "1" {
        Write-Host "正在创建便携版..." -ForegroundColor Green
        npm run pack
        $buildTypeText = "便携版"
    }
    "2" {
        Write-Host "正在制作安装包..." -ForegroundColor Green
        npm run build
        $buildTypeText = "安装包"
    }
    "3" {
        Write-Host "正在制作所有版本..." -ForegroundColor Green
        npm run dist
        $buildTypeText = "所有版本"
    }
    "4" {
        exit 0
    }
    default {
        Write-Host "无效选择，默认制作安装包..." -ForegroundColor Yellow
        npm run build
        $buildTypeText = "安装包"
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ 构建失败！" -ForegroundColor Red
    Write-Host "请检查错误信息并重试" -ForegroundColor Yellow
    Read-Host "按Enter键退出"
    exit 1
}

Write-Host ""
Write-Host "✅ $buildTypeText 构建完成！" -ForegroundColor Green
Write-Host ""

# 显示构建结果
if (Test-Path "dist") {
    $distPath = Resolve-Path "dist"
    Write-Host "构建文件位置: $distPath" -ForegroundColor Cyan
    Write-Host ""
    
    $files = Get-ChildItem -Path "dist" -File
    if ($files.Count -gt 0) {
        Write-Host "生成的文件:" -ForegroundColor Cyan
        foreach ($file in $files) {
            $sizeKB = [math]::Round($file.Length / 1KB, 2)
            $sizeMB = [math]::Round($file.Length / 1MB, 2)
            if ($sizeMB -gt 1) {
                Write-Host "  - $($file.Name) ($sizeMB MB)" -ForegroundColor White
            } else {
                Write-Host "  - $($file.Name) ($sizeKB KB)" -ForegroundColor White
            }
        }
        
        $totalSize = ($files | Measure-Object -Property Length -Sum).Sum
        $totalMB = [math]::Round($totalSize / 1MB, 2)
        Write-Host ""
        Write-Host "总大小: $totalMB MB" -ForegroundColor Yellow
    }
    
    Write-Host ""
    $openFolder = Read-Host "是否打开构建文件夹? (y/n)"
    if ($openFolder -eq "y" -or $openFolder -eq "Y") {
        Start-Process explorer.exe -ArgumentList $distPath
    }
} else {
    Write-Host "⚠️  未找到构建输出文件夹" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "构建脚本执行完成！" -ForegroundColor Green
Read-Host "按Enter键退出"
