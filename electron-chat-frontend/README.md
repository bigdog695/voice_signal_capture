# AI Chat Frontend

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

### 安装依赖
```bash
cd electron-chat-frontend
npm install
```

### 运行开发版本
```bash
npm run dev
```

### 构建应用
```bash
npm run build
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
├── index.html           # 应用HTML页面
├── styles.css           # 样式文件
├── renderer.js          # 渲染进程脚本
└── README.md           # 说明文档
```

## 自定义配置

### AI模型参数
- **模型选择**: 支持GPT-3.5、GPT-4、Claude等
- **最大Token数**: 控制回复长度
- **温度参数**: 控制回复的创造性（0-2）

### WebSocket设置
- **服务器地址**: 可配置不同的后端地址
- **自动重连**: 支持断线自动重连
- **连接状态**: 实时显示连接状态

## 开发说明

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

## 许可证

MIT License
