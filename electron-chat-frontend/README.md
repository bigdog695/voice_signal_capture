# 12345智能助手 Frontend

这是一个基于Electron的AI聊天前端应用，可以通过WebSocket与后端AI服务进行实时通信。

## 功能特性

- 💬 **实时聊天**: 类似ChatGPT的聊天界面
- 🔌 **WebSocket连接**: 与后端AI服务实时通信
- 📚 **聊天历史**: 自动保存和管理多个聊天会话
- ⚙️ **设置配置**: 可配置WebSocket地址、AI模型参数等
- 🎨 **现代UI**: 美观的用户界面，支持深色侧边栏
- 📱 **响应式设计**: 适配不同屏幕尺寸
- 🔄 **自动重连**: WebSocket断线自动重连机制

## 安装和运行

### 前置要求
- Node.js (版本 14 或更高)
- npm 或 yarn

### 清理旧产物并构建（建议）
```powershell
cd electron-chat-frontend
# 清理旧的前端构建产物
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
# 安装依赖并准备离线 UMD 资源
npm install
npm run prepare
# 构建前端（Vite）
npm run build:react
# 打包 Electron 应用（输出到 release/）
npm run pack
```

### 开发模式（同时启动 UI 与 Electron）
```powershell
cd electron-chat-frontend
npm run dev:full
```

### 运行开发版本
```bash
npm run dev
```

### 构建应用
```bash
npm run build
```

### 打包前确保离线资源
离线运行依赖 `vendor/` 目录中的 React UMD 文件。构建/打包顺序建议：
```bash
npm install
npm run prepare   # 复制 react*.js 并做大小完整性校验
npm run build
```
`package.json` 中如需保证自动复制，可在自定义流水线里显式执行 `npm run prepare`。

验证文件存在与大小（大概范围：react ≈45KB，react-dom ≈130KB）：
```bash
dir vendor
```
若大小明显小于 30KB / 80KB，则说明依赖损坏，需要：
```bash
Remove-Item -Recurse -Force node_modules
npm install
npm run prepare
```


## 使用方法

### 1. 启动应用
运行 `npm run dev` 启动应用

### 2. 配置WebSocket连接
1. 点击左下角的"Settings"按钮
2. 在"WebSocket Server URL"中输入后端地址（默认: ws://localhost:8080）
3. 配置AI模型参数
4. 点击"Save"保存设置

### 3. 开始聊天
1. 在底部输入框中输入消息
2. 按Enter或点击发送按钮发送消息
3. 等待AI回复

### 4. 管理聊天
- **新建聊天**: 点击"New Chat"按钮
- **切换聊天**: 点击左侧聊天历史中的任意聊天
- **清空聊天**: 点击聊天标题旁的垃圾桶图标

## WebSocket协议

### 发送消息格式
```json
{
  "type": "chat",
  "message": "用户输入的消息",
  "chatId": "聊天会话ID",
  "model": "gpt-3.5-turbo",
  "maxTokens": 2000,
  "temperature": 0.7,
  "history": [
    {
      "role": "user",
      "content": "历史消息",
      "timestamp": "2023-..."
    }
  ]
}
```

### 接收消息格式
```json
{
  "type": "chat_response",
  "chatId": "聊天会话ID",
  "message": "AI回复的消息"
}
```

### 错误消息格式
```json
{
  "type": "error",
  "message": "错误描述"
}
```

## 后端WebSocket服务器示例

您需要创建一个WebSocket服务器来处理聊天请求。以下是一个简单的Node.js示例：

```javascript
const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', (ws) => {
  console.log('客户端已连接');

  ws.on('message', async (message) => {
    try {
      const data = JSON.parse(message);
      
      if (data.type === 'chat') {
        // 这里调用您的AI服务
        const aiResponse = await callAIService(data.message, data.history);
        
        ws.send(JSON.stringify({
          type: 'chat_response',
          chatId: data.chatId,
          message: aiResponse
        }));
      }
    } catch (error) {
      ws.send(JSON.stringify({
        type: 'error',
        message: '处理请求时出错'
      }));
    }
  });

  ws.on('close', () => {
    console.log('客户端已断开连接');
  });
});
```

## 文件结构

```
electron-chat-frontend/
├── package.json          # 项目配置和依赖
├── main.js              # Electron主进程
├── index.html           # 最小HTML壳，只包含根节点与离线加载逻辑
├── styles.css           # 样式文件
├── renderer-react.js    # 离线Fallback使用的 UMD 版 React 渲染入口（无需打包即可运行）
├── vendor/              # 从 node_modules 复制的 React/ReactDOM UMD 离线资产
└── README.md            # 说明文档
```

## 自定义配置

### AI模型参数
- **模型选择**: 支持GPT-3.5、GPT-4、Claude等
- **最大Token数**: 控制回复长度
- **温度参数**: 控制回复的创造性（0-2）

### WebSocket设置
- **服务器地址**: 可配置不同的后端地址（持久化于 localStorage + 用户配置文件）
- **Listening 监听**: 提供单独 listening 通道的连接/停止与日志视图
- **连接测试**: 测试按钮同时请求 /health 与 /listening WebSocket 探活
- **事件日志**: 记录 open / message / close(code, reason) / error 事件

## 开发说明

### React Only 渲染架构
生产/开发模式使用 Vite 打包的 React 入口 (`src/main.jsx`)；在无 dev server（file:// 协议）且未构建 dist 的情况下，`index.html` 会加载本地 `vendor/react*.js` UMD 版本，并执行 `renderer-react.js`，它以 `document.getElementById('root')` 为挂载点完成与正式版本一致的 UI 与逻辑。已移除旧的纯 JavaScript DOM 版本（renderer.js）。

### 离线 Fallback（可选）
默认构建产物已经包含打包后的 React 代码，`loader.js` 已在生产 HTML 中移除以避免多余 vendor 404。若你需要一个“未构建 dist 也能启动”的离线回退模式，可在 `index.html` 中临时加入：
```html
<script type="module" src="./loader.js"></script>
```
前提：执行过 `npm run prepare`，确保 `vendor/react*.js` 存在。

### 离线策略
不依赖任何 CDN：React 与 ReactDOM 的 UMD 文件在 `npm install` 时通过 `prepare` 脚本从 `node_modules` 复制至 `vendor/`。安装、打包与运行均可在完全离线环境完成。

### 主要组件

1. **WebSocketManager**: 管理WebSocket连接和重连逻辑
2. **ChatManager**: 管理聊天会话、消息和UI更新
3. **UI组件**: 聊天界面、设置模态框等

### 数据存储
- 聊天历史保存在localStorage中
- 设置配置保存在localStorage中
- 支持多个聊天会话的管理

### 扩展功能
- 可以添加更多AI模型支持
- 可以集成语音输入/输出
- 可以添加文件上传功能
- 可以集成Markdown渲染

## 故障排除

### 常见问题

1. **WebSocket连接失败**
   - 检查后端服务是否运行
   - 确认WebSocket地址配置正确
   - 检查防火墙设置

2. **消息发送失败**
   - 确认WebSocket连接状态
   - 检查消息格式是否正确
   - 查看控制台错误信息

3. **应用启动失败**
   - 确认Node.js版本兼容性
   - 重新安装依赖 `npm install`
   - 检查Electron版本

## 安全说明（重要）
- 主进程 `main.js` 已调整为更安全的默认配置：
  - `nodeIntegration` 已禁用（`false`）
  - `contextIsolation` 已启用（`true`）
  - 新增 `preload.js`，通过 `contextBridge` 暴露最小化的、安全的通信 API（`window.electronAPI.send/on/once`）给渲染进程。
- 推荐做法：不要在渲染器中直接调用 Node API 或 `require('electron')`。若必须，请在 `preload.js` 中实现受限的桥接函数并白名单渠道。
- CSP：生产环境的 `dist/index.html` 已包含基本的 Content-Security-Policy meta，以减少脚本注入风险。你可以进一步收紧 `style-src` 与 `connect-src` 规则以适配你的后端域名。

## 许可证

MIT License
