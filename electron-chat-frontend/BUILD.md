# 构建安装包指南

本文档说明如何使用构建脚本为12345智能助手应用创建安装包。

## 🚀 快速开始

### 方法1: 使用批处理脚本 (推荐)
```bash
# 双击运行
build.bat

# 或在命令行中运行
build.bat
```

### 方法2: 使用PowerShell脚本
```powershell
# 在PowerShell中运行
.\build.ps1

# 或指定构建类型
.\build.ps1 -BuildType "2"  # 直接制作安装包
```

### 方法3: 使用npm命令
```bash
# 制作安装包
npm run build

# 制作便携版
npm run pack

# 制作所有版本
npm run dist

# 仅Windows版本
npm run build:win
```

## 📦 构建选项

### 1. 便携版 (Portable)
- 文件名: `12345智能助手-Portable-1.0.0.exe`
- 特点: 无需安装，直接运行
- 适合: 临时使用或不想安装的用户

### 2. 安装包 (NSIS Installer)
- 文件名: `12345智能助手-Setup-1.0.0.exe`
- 特点: 标准Windows安装程序
- 功能: 
  - 自定义安装路径
  - 创建桌面快捷方式
  - 创建开始菜单项
  - 注册表集成
  - 完整的卸载功能

### 3. 所有版本
- 同时生成便携版和安装包
- 适合发布时使用

## 📋 构建要求

### 必需软件
- Node.js (v14或更高版本)
- npm (随Node.js安装)

### 可选图标文件
将以下图标文件放入 `assets/` 文件夹:
- `icon.ico` - Windows图标 (多尺寸ICO文件)
- `icon.icns` - macOS图标 (如果需要Mac版本)
- `icon.png` - Linux图标 (512x512 PNG)

## 🔧 构建配置

### 修改应用信息
编辑 `electron-builder.json` 文件：

```json
{
  "appId": "com.yourcompany.aichat",
  "productName": "你的应用名",
  "copyright": "Copyright © 2025 你的公司",
  "publisherName": "你的公司名"
}
```

### 自定义安装程序
编辑 `installer.nsh` 文件来自定义安装过程：
- 修改安装提示信息
- 添加自定义安装步骤
- 设置文件关联

## 📁 输出文件

构建完成后，在 `dist/` 文件夹中找到以下文件：

```
dist/
├── 12345智能助手-Setup-1.0.0.exe     # Windows安装包
├── 12345智能助手-Portable-1.0.0.exe  # Windows便携版
├── 12345智能助手-1.0.0.dmg           # macOS安装包 (如果构建Mac版本)
└── 12345智能助手-1.0.0.AppImage      # Linux安装包 (如果构建Linux版本)
```

## 🛠 故障排除

### 常见问题

1. **构建失败 - 依赖错误**
   ```bash
   # 删除node_modules重新安装
   rmdir /s node_modules
   npm install
   ```

2. **图标警告**
   - 可以忽略，会使用默认图标
   - 或添加正确的图标文件到assets文件夹

3. **权限错误**
   - 以管理员身份运行构建脚本
   - 或使用PowerShell脚本

4. **构建速度慢**
   - 首次构建需要下载Electron二进制文件
   - 后续构建会快很多

### 调试模式
```bash
# 显示详细构建信息
npm run build -- --verbose

# 不压缩文件 (调试用)
npm run build -- --publish=never --debug
```

## 🚀 发布准备

### 构建前检查清单
- [ ] 更新版本号 (package.json)
- [ ] 准备图标文件
- [ ] 测试应用功能
- [ ] 检查依赖项
- [ ] 更新README和说明文档

### 发布版本构建
```bash
# 生产环境构建
npm run dist

# 检查文件大小和内容
# 测试安装包功能
# 在不同系统上测试
```

## 📊 构建统计

典型构建文件大小：
- 便携版: ~150-200 MB
- 安装包: ~150-200 MB
- 总体积取决于依赖项数量

构建时间：
- 首次构建: 5-10分钟
- 后续构建: 2-5分钟

## 🔗 相关链接

- [Electron Builder文档](https://www.electron.build/)
- [NSIS文档](https://nsis.sourceforge.io/Docs/)
- [图标制作工具](https://www.icoconverter.com/)

---

**注意**: 首次构建可能需要较长时间，因为需要下载Electron运行时文件。请确保网络连接稳定。
