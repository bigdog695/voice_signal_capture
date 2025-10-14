#!/bin/bash
# Ollama多节点启动脚本
# 用于启动多个DeepSeek 14B节点实现负载均衡

set -e

# 配置
MODEL_NAME="deepseek-r1:14b"
NODE_PORTS=(11434 11435 11436)  # 可根据需要添加更多端口
BASE_DIR="/tmp/ollama"
# 共享模型目录（所有节点共用，避免重复下载）
SHARED_MODELS_DIR="${OLLAMA_MODELS:-$HOME/.ollama/models}"

echo "================================================"
echo "启动 Ollama 多节点集群"
echo "================================================"
echo "共享模型目录: $SHARED_MODELS_DIR"
echo ""

# 创建数据目录
mkdir -p "$BASE_DIR"

# 启动各个节点
for PORT in "${NODE_PORTS[@]}"; do
    echo ""
    echo "启动节点: 端口 $PORT"
    echo "----------------------------------------"

    # 创建节点专用目录（仅存储日志）
    NODE_DIR="$BASE_DIR/node_$PORT"
    mkdir -p "$NODE_DIR"

    # 检查端口是否已被占用
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠️  端口 $PORT 已被占用，跳过..."
        continue
    fi

    # 启动Ollama服务（共享模型目录）
    OLLAMA_HOST=127.0.0.1:$PORT \
    OLLAMA_MODELS="$SHARED_MODELS_DIR" \
    nohup ollama serve > "$NODE_DIR/ollama.log" 2>&1 &

    PID=$!
    echo "✓ 节点已启动 (PID: $PID, 端口: $PORT)"
    echo "  日志文件: $NODE_DIR/ollama.log"
    echo "  模型目录: $SHARED_MODELS_DIR (共享)"

    # 等待服务启动
    sleep 2

    # 验证服务是否正常
    if curl -s http://127.0.0.1:$PORT/ >/dev/null 2>&1; then
        echo "✓ 节点健康检查通过"
    else
        echo "✗ 节点启动失败，请检查日志"
    fi
done

echo ""
echo "================================================"
echo "等待所有节点完全启动..."
echo "================================================"
sleep 3

# 只在第一个节点上加载模型（其他节点自动共享）
echo ""
echo "================================================"
echo "加载模型: $MODEL_NAME"
echo "================================================"

FIRST_PORT="${NODE_PORTS[0]}"
echo "使用节点 $FIRST_PORT 加载模型..."

# 检查模型是否已存在
if OLLAMA_HOST=127.0.0.1:$FIRST_PORT ollama list | grep -q "$MODEL_NAME"; then
    echo "✓ 模型已存在: $MODEL_NAME"
else
    echo "开始下载模型（可能需要较长时间）..."
    OLLAMA_HOST=127.0.0.1:$FIRST_PORT ollama pull "$MODEL_NAME"
    echo "✓ 模型下载完成"
fi

echo ""
echo "验证所有节点可以访问模型..."
for PORT in "${NODE_PORTS[@]}"; do
    if OLLAMA_HOST=127.0.0.1:$PORT ollama list | grep -q "$MODEL_NAME" 2>/dev/null; then
        echo "  ✓ 节点 $PORT: 模型可用"
    else
        echo "  ⚠️  节点 $PORT: 模型不可用（可能需要稍等）"
    fi
done

echo ""
echo "================================================"
echo "集群启动完成！"
echo "================================================"
echo ""
echo "节点列表:"
for PORT in "${NODE_PORTS[@]}"; do
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "  ✓ http://127.0.0.1:$PORT"
    else
        echo "  ✗ http://127.0.0.1:$PORT (未运行)"
    fi
done

echo ""
echo "环境变量配置:"
ENDPOINTS=$(printf "http://127.0.0.1:%s/api/generate," "${NODE_PORTS[@]}")
ENDPOINTS=${ENDPOINTS%,}  # 移除末尾逗号
echo "export DEEPSEEK_ENDPOINTS=\"$ENDPOINTS\""

# 导出环境变量
export DEEPSEEK_ENDPOINTS="$ENDPOINTS"
echo ""
echo "✓ 环境变量已设置: DEEPSEEK_ENDPOINTS"

echo ""
echo "启动工单服务..."
echo "----------------------------------------"

# 检查Python和依赖
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "✗ 未找到Python，请先安装Python"
    exit 1
fi

PYTHON_CMD=$(command -v python3 || command -v python)

# 检查app.py是否存在
if [ ! -f "app.py" ]; then
    echo "✗ 未找到app.py文件"
    exit 1
fi

# 启动工单服务（后台运行）
SERVICE_LOG_DIR="$BASE_DIR/service_logs"
mkdir -p "$SERVICE_LOG_DIR"

SERVICE_LOG_FILE="$SERVICE_LOG_DIR/service.log"
SERVICE_PID_FILE="$BASE_DIR/service.pid"

echo "使用命令: $PYTHON_CMD app.py"
echo "日志文件: $SERVICE_LOG_FILE"
echo ""

# 后台启动服务
nohup $PYTHON_CMD app.py > "$SERVICE_LOG_FILE" 2>&1 &
SERVICE_PID=$!

# 保存PID
echo $SERVICE_PID > "$SERVICE_PID_FILE"

echo "================================================"
echo "服务启动完成！"
echo "================================================"
echo ""
echo "工单服务:"
echo "  ✓ PID: $SERVICE_PID"
echo "  ✓ 端口: 8001"
echo "  ✓ URL: http://127.0.0.1:8001"
echo "  ✓ 日志: $SERVICE_LOG_FILE"
echo ""
echo "Ollama节点日志:"
for PORT in "${NODE_PORTS[@]}"; do
    echo "  - tail -f $BASE_DIR/node_$PORT/ollama.log"
done
echo ""
echo "工单服务日志:"
echo "  - tail -f $SERVICE_LOG_FILE"
echo ""
echo "停止所有服务:"
echo "  - ./stop_ollama_cluster.sh"
echo ""
echo "查看服务状态:"
echo "  - curl http://127.0.0.1:8001/health"
echo "  - curl http://127.0.0.1:8001/lb-stats"
echo ""

# 等待服务启动
sleep 3

# 验证服务是否运行
if ps -p $SERVICE_PID > /dev/null 2>&1; then
    echo "✓ 工单服务运行正常"

    # 测试健康检查
    if curl -s http://127.0.0.1:8001/health > /dev/null 2>&1; then
        echo "✓ 健康检查通过"
    else
        echo "⚠️  服务可能仍在启动中，请稍后访问"
    fi
else
    echo "✗ 服务启动失败，请检查日志: $SERVICE_LOG_FILE"
    exit 1
fi

echo ""
echo "================================================"

