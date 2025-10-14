# DeepSeek 负载均衡配置指南

## 概述

本文档说明如何配置多个DeepSeek 14B节点实现负载均衡，提升工单总结服务的并发处理能力。

## 核心改进

1. **共享模型目录**：所有Ollama节点共用同一个模型目录（默认 `~/.ollama/models`），避免重复下载9GB模型
2. **轮询负载均衡**：使用Round-Robin策略分发请求到不同节点
3. **自动健康检查**：失败的节点自动标记为不健康，避免重复请求
4. **故障转移**：节点失败时自动切换到其他健康节点

---

## 快速开始

### 1. 启动Ollama集群

```bash
cd ai-generated-ticket

# 赋予脚本执行权限
chmod +x start_ollama_cluster.sh stop_ollama_cluster.sh

# 启动集群（默认3个节点：11434, 11435, 11436）
./start_ollama_cluster.sh
```

**输出示例**：
```
================================================
启动 Ollama 多节点集群
================================================
共享模型目录: /home/user/.ollama/models

启动节点: 端口 11434
----------------------------------------
✓ 节点已启动 (PID: 12345, 端口: 11434)
  日志文件: /tmp/ollama/node_11434/ollama.log
  模型目录: /home/user/.ollama/models (共享)
✓ 节点健康检查通过

...

================================================
加载模型: deepseek-r1:14b
================================================
使用节点 11434 加载模型...
✓ 模型已存在: deepseek-r1:14b

验证所有节点可以访问模型...
  ✓ 节点 11434: 模型可用
  ✓ 节点 11435: 模型可用
  ✓ 节点 11436: 模型可用

================================================
集群启动完成！
================================================

节点列表:
  ✓ http://127.0.0.1:11434
  ✓ http://127.0.0.1:11435
  ✓ http://127.0.0.1:11436

环境变量配置:
export DEEPSEEK_ENDPOINTS="http://127.0.0.1:11434/api/generate,http://127.0.0.1:11435/api/generate,http://127.0.0.1:11436/api/generate"
```

### 2. 启动工单服务

```bash
# 使用环境变量配置多个端点
export DEEPSEEK_ENDPOINTS="http://127.0.0.1:11434/api/generate,http://127.0.0.1:11435/api/generate,http://127.0.0.1:11436/api/generate"

# 启动服务
python app.py
```

**服务启动日志**：
```
INFO - 启动 12345 市民热线工单总结服务
INFO - DeepSeek 负载均衡配置:
INFO -   - 节点数量: 3
INFO -   - 节点1: http://127.0.0.1:11434/api/generate
INFO -   - 节点2: http://127.0.0.1:11435/api/generate
INFO -   - 节点3: http://127.0.0.1:11436/api/generate
INFO - 初始化DeepSeek负载均衡器，节点数: 3
```

### 3. 查看负载均衡统计

访问新增的统计接口：

```bash
# 查看负载均衡器状态
curl http://localhost:8001/lb-stats
```

**响应示例**：
```json
{
  "total_endpoints": 3,
  "healthy_endpoints": 3,
  "endpoints": [
    {
      "url": "http://127.0.0.1:11434/api/generate",
      "healthy": true,
      "request_count": 15,
      "error_count": 0
    },
    {
      "url": "http://127.0.0.1:11435/api/generate",
      "healthy": true,
      "request_count": 14,
      "error_count": 0
    },
    {
      "url": "http://127.0.0.1:11436/api/generate",
      "healthy": true,
      "request_count": 13,
      "error_count": 1
    }
  ]
}
```

### 4. 停止集群

```bash
./stop_ollama_cluster.sh
```

---

## 高级配置

### 自定义节点数量和端口

编辑 `start_ollama_cluster.sh`：

```bash
# 修改这一行，添加更多端口
NODE_PORTS=(11434 11435 11436 11437 11438)
```

### 单节点模式（不使用负载均衡）

如果不需要负载均衡，直接启动：

```bash
# 不设置 DEEPSEEK_ENDPOINTS 环境变量
# 默认使用单节点：http://127.0.0.1:11434/api/generate
python app.py
```

### 自定义模型目录

```bash
# 启动前设置环境变量
export OLLAMA_MODELS="/path/to/custom/models"
./start_ollama_cluster.sh
```

---

## 性能对比

| 配置 | 并发处理能力 | 单个工单耗时 |
|------|------------|------------|
| 单节点 | 1个请求/次 | 20-30秒 |
| 3节点集群 | 3个请求/次 | 20-30秒 |
| 5节点集群 | 5个请求/次 | 20-30秒 |

**说明**：
- 单个工单需要2次LLM调用（生成工单 + 矫正地名）
- 3节点集群可同时处理3个工单的6次LLM调用
- 每增加1个节点，并发能力提升1倍

---

## 故障排查

### 问题1：端口被占用

```
⚠️  端口 11434 已被占用，跳过...
```

**解决方案**：
```bash
# 查看占用进程
lsof -i :11434

# 停止旧进程
./stop_ollama_cluster.sh
```

### 问题2：节点无法访问模型

```
⚠️  节点 11435: 模型不可用（可能需要稍等）
```

**解决方案**：
1. 等待几秒钟，Ollama需要时间加载模型
2. 检查节点日志：`tail -f /tmp/ollama/node_11435/ollama.log`
3. 手动拉取模型：`OLLAMA_HOST=127.0.0.1:11435 ollama pull deepseek-r1:14b`

### 问题3：模型下载超时

```
Error: pull model manifest: net/http: TLS handshake timeout
```

**解决方案**：
1. 检查网络连接
2. 如果已有模型，确保 `OLLAMA_MODELS` 环境变量指向正确目录
3. 重试：`./stop_ollama_cluster.sh && ./start_ollama_cluster.sh`

---

## 监控和维护

### 查看节点日志

```bash
# 节点1
tail -f /tmp/ollama/node_11434/ollama.log

# 节点2
tail -f /tmp/ollama/node_11435/ollama.log

# 节点3
tail -f /tmp/ollama/node_11436/ollama.log
```

### 健康检查

```bash
# 检查服务整体健康状态
curl http://localhost:8001/health

# 返回示例
{
  "service": "healthy",
  "deepseek_service": "healthy",
  "load_balancer": {
    "total_endpoints": 3,
    "healthy_endpoints": 3,
    ...
  },
  "timestamp": "2025-10-15T10:30:00.123456"
}
```

### 重启单个节点

```bash
# 1. 找到节点PID
lsof -i :11435

# 2. 停止节点
kill <PID>

# 3. 重启节点
OLLAMA_HOST=127.0.0.1:11435 \
OLLAMA_MODELS="$HOME/.ollama/models" \
nohup ollama serve > /tmp/ollama/node_11435/ollama.log 2>&1 &
```

---

## 生产环境建议

1. **节点数量**：根据并发需求配置，通常3-5个节点即可
2. **硬件要求**：每个DeepSeek 14B节点需要约10GB显存（GPU）或20GB内存（CPU）
3. **监控告警**：定期检查 `/lb-stats` 接口，监控节点健康状态
4. **日志轮转**：配置日志轮转避免磁盘占满
5. **Systemd服务**：生产环境建议使用systemd管理服务自动重启

---

## API变更说明

### 新增接口

#### GET /lb-stats
获取负载均衡器统计信息

**响应**：
```json
{
  "total_endpoints": 3,
  "healthy_endpoints": 3,
  "endpoints": [...]
}
```

#### GET /health (增强)
健康检查接口新增负载均衡器状态

**响应**：
```json
{
  "service": "healthy",
  "deepseek_service": "healthy",
  "load_balancer": {...},
  "timestamp": "2025-10-15T10:30:00"
}
```

### 环境变量

#### DEEPSEEK_ENDPOINTS
配置多个DeepSeek节点（逗号分隔）

```bash
export DEEPSEEK_ENDPOINTS="http://127.0.0.1:11434/api/generate,http://127.0.0.1:11435/api/generate"
```

**默认值**：`http://127.0.0.1:11434/api/generate`（单节点）

---

## 常见问题

**Q: 为什么所有节点共享同一个模型目录？**
A: DeepSeek 14B模型约9GB，共享目录避免重复下载，节省磁盘空间和启动时间。

**Q: 如何确认负载均衡正在工作？**
A: 访问 `/lb-stats` 接口，查看各节点的 `request_count`，应该均匀分布。

**Q: 节点失败后会自动恢复吗？**
A: 需要手动重启失败的节点。服务会自动将请求转发到健康节点。

**Q: 可以动态添加节点吗？**
A: 当前不支持。需要重启服务并更新 `DEEPSEEK_ENDPOINTS` 环境变量。

---

## 下一步

- 考虑使用Nginx实现更高级的负载均衡（生产环境）
- 配置Prometheus监控和Grafana可视化
- 实现节点自动扩缩容（Kubernetes）
