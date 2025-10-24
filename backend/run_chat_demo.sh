#!/bin/bash
# 启动 Chat with Video 演示界面

set -e

echo "=========================================="
echo "Chat with Video - 演示界面"
echo "=========================================="

# 设置代理
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

# 进入脚本所在目录
cd "$(dirname "$0")"

# 加载环境变量
if [ -f "../.env" ]; then
    echo "从 ../.env 加载环境变量..."
    export $(grep -v '^#' ../.env | xargs)
elif [ -f ".env" ]; then
    echo "从 .env 加载环境变量..."
    export $(grep -v '^#' .env | xargs)
fi

# 映射 API Key
if [ -n "$QWEN_API_KEY" ]; then
    export DASHSCOPE_API_KEY="$QWEN_API_KEY"
    echo "✓ API Key 已配置"
fi

# 检查后端服务
echo ""
echo "⚠️  注意: 请确保后端 API 服务已在 http://localhost:8000 运行"
echo "   如果未运行，请在另一个终端执行:"
echo "   cd backend && python -m uvicorn app.main:app --reload"
echo ""

# 启动 Gradio 界面
echo "启动 Chat 演示界面..."
echo "访问地址: http://localhost:7861"
echo ""

python3 gradio_chat_demo.py
