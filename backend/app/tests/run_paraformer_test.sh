#!/bin/bash

# 测试 Paraformer-v2 语音识别服务
# 使用方法: ./run_paraformer_test.sh

echo "=========================================="
echo "测试 Paraformer-v2 语音识别服务"
echo "=========================================="
echo ""

# 进入项目根目录
cd "$(dirname "$0")/../.." || exit

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  警告: 未检测到虚拟环境"
    echo "建议先激活虚拟环境: source venv/bin/activate"
    echo ""
fi

# 检查 API Key
if [ -z "$TRANSCRIPT_SERVICE_API_KEY" ] && [ -z "$QWEN_API_KEY" ] && [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "❌ 错误: 未设置 API Key"
    echo ""
    echo "请设置以下环境变量之一:"
    echo "  export TRANSCRIPT_SERVICE_API_KEY='your-api-key'"
    echo "  export QWEN_API_KEY='your-api-key'"
    echo "  export DASHSCOPE_API_KEY='your-api-key'"
    echo ""
    exit 1
fi

echo "✅ API Key 已设置"
echo ""

# 运行测试
echo "开始运行 Paraformer 测试..."
echo ""

python backend/app/tests/test_paraformer_service.py

echo ""
echo "测试完成!"
