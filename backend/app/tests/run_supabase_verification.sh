#!/bin/bash

# Supabase 数据持久化验证 Shell 脚本
# 
# 用途: 快速验证 Supabase 中的数据持久化
# 
# 使用方法:
#   bash run_supabase_verification.sh              # 验证所有数据
#   bash run_supabase_verification.sh <user_id>   # 验证特定用户
#   bash run_supabase_verification.sh <video_id>  # 验证特定视频

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "📍 项目根目录: $PROJECT_ROOT"
echo "📍 Backend 目录: $BACKEND_DIR"
echo ""

# 检查 Python 环境
if ! command -v python &> /dev/null; then
    echo "❌ Python 未找到，请先安装 Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "✅ Python 版本: $PYTHON_VERSION"
echo ""

# 检查 Supabase 库
echo "检查依赖..."
if ! python -c "import supabase" 2>/dev/null; then
    echo "⚠️  未找到 supabase 库，正在安装..."
    pip install supabase -q
fi
echo "✅ Supabase 库已就绪"
echo ""

# 检查环境变量
echo "检查环境变量..."
if [ ! -f "$PROJECT_ROOT/.env" ] && [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "❌ 未找到 .env 文件"
    echo "   请在 $PROJECT_ROOT 或 $BACKEND_DIR 中创建 .env 文件"
    exit 1
fi
echo "✅ .env 文件已找到"
echo ""

# 运行验证脚本
cd "$BACKEND_DIR"

echo "开始验证 Supabase 数据持久化..."
echo "=================================================="
echo ""

if [ -z "$1" ]; then
    # 验证所有数据
    python "$SCRIPT_DIR/verify_supabase_persistence.py"
elif [[ "$1" == "user:"* ]]; then
    # 验证特定用户
    USER_ID="${1#user:}"
    python "$SCRIPT_DIR/verify_supabase_persistence.py" --user-id "$USER_ID"
elif [[ "$1" == "video:"* ]]; then
    # 验证特定视频
    VIDEO_ID="${1#video:}"
    python "$SCRIPT_DIR/verify_supabase_persistence.py" --video-id "$VIDEO_ID"
else
    # 自动判断是用户ID还是视频ID
    if [[ "$1" == *"-"* ]]; then
        # 包含 "-" 的是 UUID（用户ID）
        python "$SCRIPT_DIR/verify_supabase_persistence.py" --user-id "$1"
    else
        # 其他的是视频ID
        python "$SCRIPT_DIR/verify_supabase_persistence.py" --video-id "$1"
    fi
fi

echo ""
echo "=================================================="
echo "✅ 验证完成！"
echo ""
