# 12345 市民热线工单总结服务

将通话语音识别文本自动转换为 12345 工单内容的 Python 服务。

## 功能特点

- **FastAPI 框架**: 高性能 HTTP 服务，自动生成 API 文档
- **DeepSeek 模型集成**: 使用本地部署的 DeepSeek 14B 模型进行文本总结
- **智能重试机制**: JSON 解析失败时自动重试
- **完整日志记录**: 记录输入输出和错误信息
- **数据验证**: 严格的输入输出格式验证
- **健康检查**: 提供服务和模型状态检查

## 安装部署

### 1. 安装依赖

```bash
cd ai-generated-ticket
pip install -r requirements.txt
```

### 2. 启动 Ollama 服务

确保本地已启动 Ollama 并加载 DeepSeek 模型：

```bash
# 安装 DeepSeek 模型
ollama pull deepseek-r1:14b

# 启动 Ollama 服务（默认端口 11434）
ollama serve
```

### 3. 启动工单服务

```bash
# 方式1：直接运行
python app.py

# 方式2：使用启动脚本
./start_service.sh
```

服务将在 `http://0.0.0.0:8001` 启动。

## API 接口

### POST /summarize

将通话记录转换为工单内容。

**请求格式:**
```json
{
  "1759649515307_4b58f788-ee1f-4949-97d4-accc71da1f23": [
    {"citizen": "停车库太吵了，我应该提供什么资料反映呢？"},
    {"hot-line": "看一下这停车库太吵是嗯。"},
    {"citizen": "晚上睡觉半夜还在想，一天到晚吵的，烦死了。"},
    {"hot-line": "就是小区停车场的地下停车场。"},
    {"citizen": "地下停车场出入口那里没有做一点隔音处理。"},
    {"hot-line": "做隔音处理啊，您是哪个小区啊？"},
    {"citizen": "六安市三十铺镇水韵东方小区。"},
    {"citizen": "靠近进门一百二十一栋。"}
  ]
}
```

**响应格式:**
```json
{
  "ticket_type": "投诉",
  "ticket_zone": "六安市三十铺镇水韵东方小区",
  "ticket_title": "水韵东方小区地下车库出入口噪音扰民",
  "ticket_content": "来电人反映水韵东方小区靠近进门一百二十一栋的地下车库出入口长期存在车辆经过减速带产生较大噪音，严重影响居民休息。物业此前未采取隔音处理措施。来电人希望相关部门督促物业落实隔音或降噪整改，解决噪音扰民问题。"
}
```

### GET /health

检查服务健康状态。

### GET /

基础状态检查。

## 使用示例

```bash
# 测试接口
curl -X POST "http://localhost:8001/summarize" \
  -H "Content-Type: application/json" \
  -d '{
    "session_123": [
      {"citizen": "停车库太吵了"},
      {"hot-line": "您是哪个小区？"},
      {"citizen": "水韵东方小区"}
    ]
  }'

# 健康检查
curl http://localhost:8001/health
```

## 配置说明

- **DeepSeek API**: `http://127.0.0.1:11434/api/generate`
- **服务端口**: `8001`
- **重试次数**: `2` 次
- **请求超时**: `60` 秒
- **日志文件**: `ticket_service.log`

## 工单类型

支持的工单类型：
- 咨询
- 求助
- 投诉
- 举报
- 建议
- 其他

## 日志记录

服务会自动记录：
- 请求接收和处理时间
- 输入数据大小和内容
- 模型调用过程
- 生成的工单内容
- 错误信息和重试过程

日志文件位置：`ticket_service.log`

## 错误处理

- **JSON 格式错误**: 返回 400 状态码
- **数据验证失败**: 返回 400 状态码
- **模型调用失败**: 自动重试，最终失败返回 500 状态码
- **JSON 解析失败**: 自动重试，清理响应格式后重新解析