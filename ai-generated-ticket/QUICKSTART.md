# 快速开始指南

## 一键启动工单服务（含负载均衡）

```bash
cd ai-generated-ticket

# 首次运行：赋予脚本执行权限
chmod +x start_ollama_cluster.sh stop_ollama_cluster.sh

# 启动服务（自动启动3个DeepSeek节点 + 工单服务）
./start_ollama_cluster.sh
```

**脚本自动完成**：
1. ✅ 启动3个Ollama节点（端口11434/11435/11436）
2. ✅ 共享模型目录（只下载1次DeepSeek 14B，节省9GB×2空间）
3. ✅ 设置负载均衡环境变量
4. ✅ 启动工单服务（http://localhost:8001）

**停止服务**：按 `Ctrl+C`

---

## 验证服务运行

### 测试负载均衡

```bash
# 查看负载均衡统计
curl http://localhost:8001/lb-stats

# 响应示例
{
  "total_endpoints": 3,
  "healthy_endpoints": 3,
  "endpoints": [
    {"url": "http://127.0.0.1:11434/api/generate", "healthy": true, "request_count": 10},
    {"url": "http://127.0.0.1:11435/api/generate", "healthy": true, "request_count": 9},
    {"url": "http://127.0.0.1:11436/api/generate", "healthy": true, "request_count": 11}
  ]
}
```

### 健康检查

```bash
curl http://localhost:8001/health
```

---

## 查看日志

```bash
# Ollama节点日志
tail -f /tmp/ollama/node_11434/ollama.log
tail -f /tmp/ollama/node_11435/ollama.log
tail -f /tmp/ollama/node_11436/ollama.log

# 工单服务日志（在启动终端查看）
```

---

## 停止服务

```bash
# 方法1：在启动终端按 Ctrl+C

# 方法2：停止所有Ollama节点
./stop_ollama_cluster.sh
```

---

## 配置说明

### 修改节点数量

编辑 `start_ollama_cluster.sh`：

```bash
# 第9行，增加或减少端口
NODE_PORTS=(11434 11435 11436 11437 11438)  # 5个节点
```

### 单节点模式（无负载均衡）

```bash
# 直接启动，不使用集群脚本
ollama serve  # 默认端口11434
python app.py  # 自动使用单节点配置
```

---

## 性能对比

| 节点数 | 并发工单数 | 模型下载次数 | 磁盘占用 |
|-------|-----------|-------------|---------|
| 1节点 | 1个/次     | 1次         | 9GB     |
| 3节点 | 3个/次     | 1次 ✅       | 9GB ✅   |
| 5节点 | 5个/次     | 1次 ✅       | 9GB ✅   |

**关键优势**：共享模型目录，无论多少节点都只下载1次！

---

## 完整文档

详细配置和故障排查请参考：[LOAD_BALANCING.md](LOAD_BALANCING.md)
