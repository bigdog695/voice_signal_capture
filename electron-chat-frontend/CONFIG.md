# 配置管理说明

## 概述

前端应用已经移除了**所有硬编码的 IP 地址和默认后端配置**，强制用户在首次使用时配置后端服务器地址。这确保了配置的明确性和可控性。

## 🎯 配置原则

1. **无默认后端地址**：应用启动时 `backendHost` 为空，必须由用户配置
2. **保留用户输入**：不自动转换 `localhost` 等地址，完全尊重用户配置
3. **统一配置入口**：所有后端 endpoint 通过 `ConfigContext.jsx` 统一生成
4. **明确的错误提示**：未配置时会显示清晰的警告信息

## 配置方式

### 1. 应用内配置（强烈推荐）✨
在应用界面中点击设置按钮，可以配置：
- **后端服务地址**: 例如 `localhost:8000`、`192.168.1.100:8000` 或 `example.com:8000`
- **使用 HTTPS/WSS**: 切换 HTTP/WS 和 HTTPS/WSS 协议

**特点**：
- ✅ 配置立即生效，无需重启
- ✅ 自动保存到用户数据目录
- ✅ 可测试连接是否正常
- ✅ 实时预览所有 endpoint

### 2. 配置文件
修改 `app-config.json` 文件（或用户数据目录中的配置文件）：
```json
{
  "default": {
    "backendHost": "",
    "useHttps": false,
    "devServerHost": "localhost:5173",
    "exampleServerHost": "localhost:8080"
  }
}
```

**配置文件位置**：
- 开发环境：项目根目录 `app-config.json`
- 生产环境：用户数据目录 `%APPDATA%\<AppName>\app-config.json` (Windows)
- 生产环境：`~/Library/Application Support/<AppName>/app-config.json` (macOS)
- 生产环境：`~/.config/<AppName>/app-config.json` (Linux)

支持的环境配置：
- `default`: 默认配置
- `development`: 开发环境配置
- `production`: 生产环境配置（自动启用 HTTPS）

通过 `NODE_ENV` 环境变量选择使用的配置环境。

### 3. 环境变量（仅限开发服务器配置）
以下环境变量**仅**用于覆盖开发相关配置：

- `DEV_SERVER_HOST`: 开发服务器地址（默认：`localhost:5173`）
- `EXAMPLE_SERVER_HOST`: 示例 WebSocket 服务器地址（默认：`localhost:8080`）

⚠️ **注意**：`backendHost` 和 `useHttps` 不能通过环境变量设置，必须通过配置文件或 UI 设置。

示例：
```bash
# Windows PowerShell
$env:DEV_SERVER_HOST="localhost:3000"

# Linux/macOS
export DEV_SERVER_HOST=localhost:3000
```

## 配置优先级

用户数据目录配置文件（最高优先级）
    ↓
项目根目录 `app-config.json`
    ↓
代码中的 `DEFAULT_CONFIG`（backendHost 为空）

**重要**：环境变量不能覆盖 `backendHost` 和 `useHttps`，只能设置开发相关的配置。

## 🏗️ 架构说明

### 统一的 Endpoint 管理

所有后端 API 和 WebSocket 连接都通过 `ConfigContext.jsx` 统一管理：

```javascript
// 统一的配置上下文
const { urls, backendHost, useHttps } = useConfig();

// 所有可用的 endpoint
urls.listening()  // WebSocket: ws://host:port/listening
urls.chat(id)     // WebSocket: ws://host:port/chatting?id=xxx
urls.asr()        // WebSocket: ws://host:port/ws
urls.health()     // HTTP: http://host:port/health
urls.base()       // HTTP: http://host:port
```

### 使用规范

✅ **正确做法**：
```jsx
import { useConfig } from '../config/ConfigContext';

function MyComponent() {
  const { urls, ready } = useConfig();
  
  if (!ready) {
    return <div>请先配置后端服务器...</div>;
  }
  
  // 使用统一的 URL
  const ws = new WebSocket(urls.listening());
  fetch(urls.health());
}
```

❌ **错误做法**（硬编码）：
```jsx
// 不要这样做！
const ws = new WebSocket('ws://192.168.1.100:8000/listening');
fetch('http://localhost:8000/health');
```

## ✅ 已移除的问题

### 1. 硬编码的 IP 地址
- ✅ 所有文件中的 `192.168.0.201:8000` 已移除
- ✅ 默认配置改为空字符串，强制用户配置

### 2. localhost 自动转换
- ✅ 移除了 `localhost` 自动转换为 `192.168.0.201` 的逻辑
- ✅ 现在完全尊重用户输入的地址
- ✅ 用户可以自由选择使用 `localhost`、`127.0.0.1` 或其他地址

### 3. 分散的配置
- ✅ 统一到 `ConfigContext.jsx` 管理
- ✅ 所有组件通过 `useConfig()` Hook 获取配置
- ✅ 无任何硬编码的 HTTP 或 WebSocket 连接

## 📝 更新的文件列表

### 核心配置文件
1. **src/modules/config/ConfigContext.jsx** - 前端统一配置上下文
   - 移除 localhost 自动转换
   - 添加配置未就绪状态管理

2. **config.js** - Electron 主进程配置管理
   - 默认 backendHost 改为空
   - 移除 localhost 自动转换
   - 添加未配置警告

3. **main.js** - Electron 主进程
   - 移除 localhost 自动转换（config:set 和 ticket generation）
   - 更新 FALLBACK 配置为空

4. **app-config.json** - 配置文件模板
   - 所有环境的 backendHost 改为空

### 其他更新文件
5. **websocket-server-example.js** - 示例服务器
   - 默认配置更新

6. **CONFIG.md** - 配置文档（本文件）
   - 完整更新配置说明和最佳实践

## 🎯 配置最佳实践

### 开发环境推荐配置

```json
{
  "default": {
    "backendHost": "localhost:8000",
    "useHttps": false
  }
}
```

### 生产环境推荐配置

```json
{
  "production": {
    "backendHost": "your-production-server.com:8000",
    "useHttps": true
  }
}
```

### IPv6 环境

如果遇到 IPv6 相关问题（例如 `::1`），请：
- 使用 `127.0.0.1:8000` 而不是 `localhost:8000`
- 或者在后端服务器配置中明确绑定 IPv4 地址

## 使用建议

1. **首次使用**: 通过应用内设置界面配置后端地址
2. **开发环境**: 使用 `localhost:8000` 或 `127.0.0.1:8000`
3. **生产环境**: 在 `app-config.json` 中配置实际服务器地址
4. **测试连接**: 使用设置界面的"测试连接"功能验证配置

## 注意事项

- ⚠️ 首次启动应用时，由于没有配置后端地址，应用会提示"请先配置后端服务器"
- ⚠️ 配置更改后，部分功能可能需要刷新页面或重启应用
- ⚠️ 确保配置的地址格式正确：`host:port`（不要加 `http://` 或 `ws://` 前缀）
- ✅ HTTPS 配置会同时影响 HTTP 和 WebSocket 连接协议（HTTP↔HTTPS, WS↔WSS）

## 离线支持（React UMD）

为使应用在没有网络访问的环境下仍能展示回退的 React UI，我们引入了本地 UMD 版本的 React 和 ReactDOM：

- 本地文件位置：`vendor/react.production.min.js` 和 `vendor/react-dom.production.min.js`
- 在 `index.html` 的 file:// 分支会优先加载这两份本地文件；若不存在或加载失败会退回到 CDN；若 CDN 也不可用，则加载纯 JS 回退 `renderer.js`。

如何生成本地 UMD 文件（推荐自动化）

- 本仓库包含脚本：`scripts/download-umd.js`，它会从本地安装的 `node_modules` 复制 React/ReactDOM 的 UMD 生产构建到 `vendor/`（请先运行 `npm install`）。
- 该脚本使应用在离线环境下可通过本地 UMD 文件运行回退 React UI。
- 在 `package.json` 中已添加 `prepare` 脚本，会在 `npm install`（或显式运行 `npm run prepare`）时执行：

  npm run prepare

- 你也可以手动把 UMD 文件放到 `vendor/` 下；之后打包（electron-builder）时 `vendor/**` 会被包含到应用包中。

注意：如果你需要完全离线打包（CI 构建环境无网络），请在 CI 流程中提前把 `vendor/` 目录包含进构建工件，或将 UMD 文件提交到仓库。