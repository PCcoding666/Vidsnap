#!/bin/bash

# 测试真实视频的 Paraformer 转录
# 视频文件: backend/app/tests/downloaded_video (1).mp4

echo "=========================================="
echo "🎬 测试真实视频 Paraformer 转录"
echo "=========================================="
echo ""

# 进入项目根目录
cd "$(dirname "$0")/../.." || exit

# 检查视频文件
VIDEO_FILE="backend/app/tests/downloaded_video (1).mp4"
if [ ! -f "$VIDEO_FILE" ]; then
    echo "❌ 错误: 视频文件不存在"
    echo "   期望路径: $VIDEO_FILE"
    echo ""
    exit 1
fi

echo "✅ 找到视频文件: $VIDEO_FILE"
echo ""

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "❌ 错误: .env 文件不存在"
    echo "   请在项目根目录创建 .env 文件并设置 API Key"
    echo ""
    exit 1
fi

echo "✅ 找到 .env 配置文件"
echo ""

# 检查是否在 Conda 环境中
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    echo "✅ 检测到 Conda 环境: $CONDA_DEFAULT_ENV"
    echo ""
elif [ -n "$VIRTUAL_ENV" ]; then
    echo "✅ 检测到虚拟环境: $VIRTUAL_ENV"
    echo ""
else
    echo "⚠️  警告: 未检测到虚拟环境"
    echo "建议先激活环境:"
    echo "  conda activate yt_summarizer"
    echo "  或"
    echo "  source venv/bin/activate"
    echo ""
fi

# 运行测试
echo "开始运行 Paraformer 真实视频测试..."
echo ""
echo "预计耗时: 2-5 分钟 (取决于视频长度)"
echo ""

python backend/app/tests/test_real_video_paraformer.py

echo ""
echo "测试完成!"
