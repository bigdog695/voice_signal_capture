#!/bin/bash
# 查看服务日志

BASE_DIR="/tmp/ollama"
LOG_DIR="$(dirname "$0")/logs"

echo "================================================"
echo "服务日志查看"
echo "================================================"
echo ""

# 显示菜单
echo "选择要查看的日志:"
echo ""
echo "工单服务日志:"
echo "  1) 实时日志（最新）"
echo "  2) 完整日志文件"
echo "  3) 历史日志（按日期）"
echo ""
echo "Ollama节点日志:"
echo "  4) 节点 11434"
echo "  5) 节点 11435"
echo "  6) 节点 11436"
echo ""
echo "  0) 退出"
echo ""
read -p "请选择 [0-6]: " choice

case $choice in
    1)
        echo ""
        echo "实时查看工单服务日志 (Ctrl+C 退出)..."
        echo "----------------------------------------"
        tail -f "$LOG_DIR/ticket_service.log"
        ;;
    2)
        echo ""
        echo "完整工单服务日志:"
        echo "----------------------------------------"
        less "$LOG_DIR/ticket_service.log"
        ;;
    3)
        echo ""
        echo "历史日志文件:"
        ls -lh "$LOG_DIR"/*.log* 2>/dev/null || echo "  未找到历史日志"
        echo ""
        read -p "输入日期文件名查看 (如 ticket_service.log.2025-10-14): " logfile
        if [ -f "$LOG_DIR/$logfile" ]; then
            less "$LOG_DIR/$logfile"
        else
            echo "文件不存在"
        fi
        ;;
    4)
        echo ""
        echo "Ollama节点 11434 日志 (Ctrl+C 退出)..."
        echo "----------------------------------------"
        tail -f "$BASE_DIR/node_11434/ollama.log"
        ;;
    5)
        echo ""
        echo "Ollama节点 11435 日志 (Ctrl+C 退出)..."
        echo "----------------------------------------"
        tail -f "$BASE_DIR/node_11435/ollama.log"
        ;;
    6)
        echo ""
        echo "Ollama节点 11436 日志 (Ctrl+C 退出)..."
        echo "----------------------------------------"
        tail -f "$BASE_DIR/node_11436/ollama.log"
        ;;
    0)
        echo "退出"
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac
