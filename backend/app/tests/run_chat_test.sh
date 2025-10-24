#!/bin/bash
# 测试视频聊天服务

set -e

echo "=========================================="
echo "视频聊天服务测试"
echo "=========================================="

# 设置代理
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

# 进入后端目录
cd "$(dirname "$0")/../.."

# 检查环境变量
if [ -z "$QWEN_API_KEY" ]; then
    echo "⚠️  警告: QWEN_API_KEY 未设置"
    
    # 尝试从 .env 文件加载
    if [ -f "../../.env" ]; then
        echo "从 ../../.env 加载环境变量..."
        export $(grep -v '^#' ../../.env | xargs)
    elif [ -f ".env" ]; then
        echo "从 .env 加载环境变量..."
        export $(grep -v '^#' .env | xargs)
    else
        echo "❌ 错误: 找不到 .env 文件"
        echo "请在项目根目录或 backend 目录下创建 .env 文件，并设置 QWEN_API_KEY"
        exit 1
    fi
fi

# 映射到 DASHSCOPE_API_KEY
if [ -n "$QWEN_API_KEY" ]; then
    export DASHSCOPE_API_KEY="$QWEN_API_KEY"
    echo "✓ API Key 已配置"
fi

# 运行测试
echo ""
echo "开始测试..."
echo ""

python3 app/tests/test_chat_service.py

echo ""
echo "=========================================="
echo "✓ 测试完成"
echo "=========================================="
