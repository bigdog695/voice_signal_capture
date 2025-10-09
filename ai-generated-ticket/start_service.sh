#!/bin/bash

# 12345 市民热线工单总结服务启动脚本

set -e

echo "=== 12345 市民热线工单总结服务 ==="
echo "正在启动服务..."

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "错误: 需要 Python 3.8 或更高版本，当前版本: $(python3 --version)"
    exit 1
fi

# 检查并安装依赖
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

echo "激活虚拟环境..."
source venv/bin/activate

echo "安装/更新依赖..."
pip install -r requirements.txt

# 检查 Ollama 服务
echo "检查 DeepSeek 模型服务..."
if ! curl -s http://127.0.0.1:11434 > /dev/null; then
    echo "警告: DeepSeek 服务 (http://127.0.0.1:11434) 不可达"
    echo "请确保 Ollama 服务正在运行，并已加载 deepseek-r1:14b 模型"
    echo "安装命令: ollama pull deepseek-r1:14b"
    echo ""
fi

# 启动服务
echo "启动工单总结服务..."
echo "服务地址: http://0.0.0.0:8001"
echo "API 文档: http://0.0.0.0:8001/docs"
echo "健康检查: http://0.0.0.0:8001/health"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python3 app.py