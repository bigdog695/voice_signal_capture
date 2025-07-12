# Voice Chat Backend with ASR

基于asr文件夹架构优化的语音聊天后端服务，支持实时语音识别和WebSocket通信。

## 功能特性

- 🎯 **实时语音聊天**: WebSocket支持的实时聊天功能
- 🎤 **语音识别**: 集成FunASR流式语音识别
- 🐳 **Docker化部署**: 完整的Docker支持，模型预下载
- 🔄 **Mock模式**: 当ASR不可用时自动降级到Mock模式
- 📋 **RESTful API**: 完整的聊天记录管理API
- 🔍 **健康检查**: 服务状态监控端点

## API 端点

### REST API

1. **获取聊天列表**
   ```
   GET /chat/list?id={user_id}
   ```
   返回指定用户的所有聊天历史

2. **获取聊天详情**
   ```
   GET /chat/{chat_id}
   ```
   返回指定聊天的详细信息和消息历史

3. **健康检查**
   ```
   GET /health
   ```
   返回服务器状态信息

### WebSocket

```
WebSocket /chatting?id={chat_id}
```
- 如果chat_id对应的会话正在进行中，建立WebSocket连接
- 如果会话已结束或不存在，拒绝连接
- 连接后推送历史消息和实时消息

## 安装和运行

### 方法1: 使用批处理文件（推荐）
```bash
# 运行 start.bat 文件，会自动安装依赖并启动服务器
start.bat
```

### 方法2: 手动安装
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务器
python main.py
```

## 服务器信息

- **端口**: 8000
- **主机**: 0.0.0.0 (所有接口)
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 示例使用

### 获取用户聊天列表
```bash
curl "http://localhost:8000/chat/list?id=user_001"
```

### WebSocket连接
```javascript
const ws = new WebSocket('ws://localhost:8000/chatting?id=chat_active_001');
```

## 数据模型

### ChatMessage
- id: 消息ID
- chat_id: 聊天ID
- speaker: 发言人 ("user" 或 "assistant")
- content: 消息内容
- timestamp: 时间戳

### ChatSession
- id: 聊天ID
- user_id: 用户ID
- title: 聊天标题
- status: 状态 ("active" 或 "ended")
- created_at: 创建时间
- ended_at: 结束时间
- messages: 消息列表

## 测试数据

系统启动时会自动创建以下测试数据：
- 用户ID: `user_001`
- 已结束的聊天: `chat_001`, `chat_002`, `chat_003`
- 活跃聊天: `chat_active_001`
