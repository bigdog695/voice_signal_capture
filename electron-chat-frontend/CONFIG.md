# 配置管理说明

## 概述

前端应用已经移除了所有硬编码的IP地址，现在支持通过多种方式进行配置管理。

## 配置方式

### 1. 应用内配置（推荐）
在应用界面中点击设置按钮，可以配置：
- 后端服务地址 (例如: `localhost:8000` 或 `192.168.1.100:8000`)
- 是否使用HTTPS/WSS协议

配置会自动保存到浏览器的localStorage中。

### 2. 配置文件
修改 `app-config.json` 文件：
```json
{
  "default": {
    "backendHost": "your-host:8000",
    "useHttps": false,
    "devServerHost": "localhost:5173",
    "exampleServerHost": "localhost:8080"
  }
}
```

支持的环境配置：
- `default`: 默认配置
- `development`: 开发环境配置
- `production`: 生产环境配置

通过 `NODE_ENV` 环境变量选择使用的配置环境。

### 3. 环境变量
可以通过以下环境变量覆盖配置：

- `BACKEND_HOST`: 后端服务地址
- `USE_HTTPS`: 是否使用HTTPS/WSS (true/false)
- `DEV_SERVER_HOST`: 开发服务器地址
- `EXAMPLE_SERVER_HOST`: 示例WebSocket服务器地址

示例：
```bash
# Windows
set BACKEND_HOST=192.168.1.100:8000
set USE_HTTPS=false

# Linux/macOS
export BACKEND_HOST=192.168.1.100:8000
export USE_HTTPS=false
```

## 配置优先级

1. 环境变量 (最高优先级)
2. 配置文件
3. 默认配置 (最低优先级)

## 已移除的硬编码地址

### ConfigContext.jsx
- ✅ 扩展了配置项，添加了开发服务器和示例服务器配置

### main.js  
- ✅ 移除了硬编码的 `http://localhost:5173`
- ✅ 现在通过配置系统获取开发服务器地址

### index.html
- ✅ 移除了所有硬编码的 `localhost:8000` 地址
- ✅ 端点预览现在动态生成

### websocket-server-example.js
- ✅ 移除了硬编码的 `localhost:8080`
- ✅ 现在通过配置系统获取端口

### SettingsModal.jsx
- ✅ 示例文本从具体IP改为通用格式

## 新增文件

1. **config.js**: 主进程配置管理模块
2. **app-config.json**: JSON格式的配置文件
3. **renderer.js**: 渲染进程配置管理，处理HTML页面的动态配置
4. **CONFIG.md**: 本说明文件

## 使用建议

1. **开发环境**: 使用默认的localhost配置即可
2. **生产环境**: 修改 `app-config.json` 中的production配置，或使用环境变量
3. **用户自定义**: 通过应用界面进行配置，设置会持久化保存

## 注意事项

- 配置更改后需要重启应用才能生效（除了应用内配置）
- 确保配置的地址格式正确：`host:port`
- HTTPS配置会同时影响HTTP和WebSocket连接协议