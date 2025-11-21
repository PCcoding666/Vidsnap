#!/bin/bash

echo "🔍 YouTube URL 测试工具"
echo "========================"

# 检查参数
if [ -z "$1" ]; then
    echo "用法: $0 <YouTube_URL>"
    echo "示例: $0 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'"
    exit 1
fi

YOUTUBE_URL="$1"

echo ""
echo "📋 测试URL: $YOUTUBE_URL"
echo ""

# 测试1: 检查网络连接
echo "1️⃣ 测试网络连接..."
if ping -c 1 youtube.com &> /dev/null; then
    echo "✅ 网络连接正常"
else
    echo "❌ 无法访问 youtube.com，请检查网络连接"
    exit 1
fi

# 测试2: 使用curl测试URL可访问性
echo ""
echo "2️⃣ 测试URL可访问性..."
HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}" "$YOUTUBE_URL")
if [ "$HTTP_CODE" -eq 200 ] || [ "$HTTP_CODE" -eq 302 ]; then
    echo "✅ URL可访问 (HTTP $HTTP_CODE)"
else
    echo "⚠️  URL返回 HTTP $HTTP_CODE"
fi

# 测试3: 测试yt-dlp下载
echo ""
echo "3️⃣ 测试 yt-dlp 下载..."
cd /Users/chengpeng/Downloads/MyProject/My_Youtube_Summarizer/backend

# 激活conda环境并测试
source /Users/chengpeng/miniconda3/etc/profile.d/conda.sh
conda activate yt_summarizer

# 设置代理
export https_proxy=http://127.0.0.1:33210
export http_proxy=http://127.0.0.1:33210
export all_proxy=socks5://127.0.0.1:33211

echo "尝试获取视频信息..."
yt-dlp --simulate --print "%(title)s - %(duration)s秒" "$YOUTUBE_URL" 2>&1 | head -20

echo ""
echo "========================"
echo "测试完成！"
