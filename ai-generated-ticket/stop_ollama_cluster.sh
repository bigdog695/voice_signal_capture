#!/bin/bash
# 停止所有Ollama节点和工单服务

set -e

echo "================================================"
echo "停止 Ollama 多节点集群和工单服务"
echo "================================================"

BASE_DIR="/tmp/ollama"
SERVICE_PID_FILE="$BASE_DIR/service.pid"

# 1. 停止工单服务
echo ""
echo "1. 停止工单服务..."
if [ -f "$SERVICE_PID_FILE" ]; then
    SERVICE_PID=$(cat "$SERVICE_PID_FILE")
    if ps -p $SERVICE_PID > /dev/null 2>&1; then
        echo "  停止工单服务 (PID: $SERVICE_PID)"
        kill $SERVICE_PID 2>/dev/null || true
        sleep 1

        # 强制杀死
        if ps -p $SERVICE_PID > /dev/null 2>&1; then
            kill -9 $SERVICE_PID 2>/dev/null || true
        fi

        rm -f "$SERVICE_PID_FILE"
        echo "  ✓ 工单服务已停止"
    else
        echo "  工单服务未运行"
        rm -f "$SERVICE_PID_FILE"
    fi
else
    echo "  未找到工单服务PID文件"
fi

# 2. 停止所有Ollama节点
echo ""
echo "2. 停止Ollama节点..."
PIDS=$(pgrep -f "ollama serve" || true)

if [ -z "$PIDS" ]; then
    echo "  没有发现运行中的Ollama节点"
else
    echo "  发现Ollama进程: $PIDS"

    # 停止所有进程
    for PID in $PIDS; do
        echo "    停止 PID: $PID"
        kill $PID 2>/dev/null || true
    done

    # 等待进程退出
    sleep 2

    # 强制杀死未退出的进程
    REMAINING=$(pgrep -f "ollama serve" || true)
    if [ -n "$REMAINING" ]; then
        echo "  强制停止剩余进程..."
        for PID in $REMAINING; do
            kill -9 $PID 2>/dev/null || true
        done
    fi

    echo "  ✓ 所有Ollama节点已停止"
fi

echo ""
echo "================================================"
echo "✓ 所有服务已停止"
echo "================================================"

