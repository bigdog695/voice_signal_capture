# Voice Chat Backend 部署和测试说明

## 项目概览
本项目是一个基于asr文件夹架构优化的语音聊天后端，集成了FunASR实时语音识别功能。

## 部署方式

### 1. 本地部署 (推荐用于开发)

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
# 或使用启动脚本
start.bat
```

### 2. Docker部署 (推荐用于生产)

#### 前提条件
- 安装并启动Docker Desktop
- 确保Docker daemon正在运行

#### 自动部署
```bash
# 使用自动化脚本
docker-test.bat
```

#### 手动部署
```bash
# 1. 构建镜像
docker build -t voice-chat-backend .

# 2. 运行容器
docker run -d \
  --name voice-chat-backend-container \
  -p 8000:8000 \
  --restart unless-stopped \
  voice-chat-backend

# 3. 查看日志
docker logs -f voice-chat-backend-container

# 4. 停止容器
docker stop voice-chat-backend-container
docker rm voice-chat-backend-container
```

## 服务端点

### HTTP API
- 根路径: http://localhost:8000
- API文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health
- ASR信息: http://localhost:8000/asr/info
- 聊天列表: http://localhost:8000/chat/list?id=user_001
- 聊天详情: http://localhost:8000/chat/{chat_id}

### WebSocket
- 聊天WebSocket: ws://localhost:8000/chatting?id={chat_id}
- ASR WebSocket: ws://localhost:8000/ws

## 测试命令

### 基本测试
```bash
# 健康检查
curl http://localhost:8000/health

# ASR服务信息
curl http://localhost:8000/asr/info

# 聊天列表
curl "http://localhost:8000/chat/list?id=user_001"
```

### WebSocket测试 (使用wscat)
```bash
# 安装wscat
npm install -g wscat

# 测试聊天WebSocket
wscat -c "ws://localhost:8000/chatting?id=test_chat_001"

# 测试ASR WebSocket (需要发送音频数据)
wscat -c "ws://localhost:8000/ws"
```

## 架构特点

### 基于asr文件夹的架构优化
- **Docker优先**: 支持完整的容器化部署
- **模型预下载**: Docker构建时自动下载FunASR模型
- **专业日志**: 结构化日志记录
- **健康检查**: 完整的服务监控端点
- **CORS配置**: 支持跨域访问

### FunASR集成
- **模型**: paraformer-zh-streaming v2.0.4
- **设备**: CPU (可配置为GPU)
- **音频格式**: 16-bit PCM, 16kHz
- **实时处理**: 流式语音识别
- **必选依赖**: FunASR是必选项，不提供Mock模式

### WebSocket特性
- **实时聊天**: 支持多用户并发聊天
- **语音识别**: 实时ASR音频流处理
- **消息合并**: 前端支持部分消息合并显示
- **错误处理**: 完善的连接和错误管理

## 故障排除

### Docker相关问题

1. **Docker Desktop未启动**
   ```
   错误: error during connect: Head "http://...": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
   
   解决方案:
   - 启动Docker Desktop应用程序
   - 等待完全启动（托盘图标不再转动）
   - 重新运行部署命令
   ```

2. **镜像构建失败**
   ```
   可能原因:
   - 网络连接问题（下载FunASR模型）
   - 磁盘空间不足
   - 依赖冲突
   
   解决方案:
   - 检查网络连接
   - 清理Docker缓存: docker system prune
   - 重新构建: docker build --no-cache -t voice-chat-backend .
   ```

3. **容器启动失败**
   ```
   检查步骤:
   - 查看日志: docker logs voice-chat-backend-container
   - 检查端口占用: netstat -an | findstr :8000
   - 验证镜像: docker images | findstr voice-chat-backend
   ```

### ASR相关问题

1. **FunASR安装失败**
   ```
   Windows下常见问题:
   - PyTorch版本不兼容
   - 缺少Visual Studio Build Tools
   
   解决方案:
   - 使用Docker部署（推荐）
   - 在Linux环境中部署
   - 使用预编译的wheel包
   ```

2. **模型下载失败**
   ```
   可能原因:
   - 网络连接问题
   - Hugging Face访问限制
   
   解决方案:
   - 配置代理
   - 使用ModelScope hub: 修改download_model.py中的hub="ms"
   ```

## 性能优化

### Docker优化
- 使用多阶段构建减少镜像大小
- 挂载模型缓存目录避免重复下载
- 配置合适的资源限制

### ASR优化
- 根据硬件配置选择CPU/GPU
- 调整chunk_size参数优化延迟
- 配置合适的look-back参数

## 监控和维护

### 健康检查
```bash
# 检查服务状态
curl http://localhost:8000/health

# 检查ASR状态
curl http://localhost:8000/asr/info

# 检查容器状态
docker ps | grep voice-chat-backend
```

### 日志监控
```bash
# 实时日志
docker logs -f voice-chat-backend-container

# 最近100行日志
docker logs --tail 100 voice-chat-backend-container
```

### 资源监控
```bash
# 容器资源使用
docker stats voice-chat-backend-container

# 系统资源
docker system df
```
