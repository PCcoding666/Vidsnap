#!/bin/bash

# 并发处理测试脚本
# 测试关键帧提取和音频转录的并发执行功能

echo "=========================================="
echo "并发处理测试"
echo "=========================================="
echo ""

# 设置项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "项目根目录: $PROJECT_ROOT"
echo "后端目录: $BACKEND_DIR"
echo ""

# 进入后端目录
cd "$BACKEND_DIR" || exit 1

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi

echo "✅ Python 版本: $(python3 --version)"
echo ""

# 运行测试
echo "=========================================="
echo "开始测试并发处理"
echo "=========================================="
echo ""

# 创建测试 Python 脚本
cat > /tmp/test_concurrent.py << 'EOF'
"""
测试并发处理功能
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

from app.services.pipeline_service import pipeline
from app.core.logging import logger

async def test_concurrent_processing():
    """测试并发处理"""
    
    # 使用一个短视频进行测试
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # 示例 URL
    
    logger.info("=" * 60)
    logger.info("测试场景: 并发执行关键帧提取和音频转录")
    logger.info("=" * 60)
    
    try:
        # 测试并发处理
        result = await pipeline.process_video_with_summary(
            youtube_url=test_url,
            user_id="test_user"
        )
        
        if result["status"] == "success":
            logger.info("✅ 并发处理测试成功!")
            logger.info(f"  - 视频ID: {result['video_id']}")
            logger.info(f"  - 关键帧数量: {result['keyframes_count']}")
            logger.info(f"  - 转录段落数量: {result['transcript_segments_count']}")
            logger.info(f"  - 总结生成: {result.get('summary_generated', False)}")
            return True
        else:
            logger.error(f"❌ 并发处理测试失败: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.exception(f"❌ 测试过程中发生异常: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_concurrent_processing())
    sys.exit(0 if success else 1)
EOF

# 运行测试
echo "运行并发处理测试..."
python3 /tmp/test_concurrent.py

TEST_RESULT=$?

# 清理临时文件
rm -f /tmp/test_concurrent.py

echo ""
echo "=========================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo "✅ 并发处理测试通过"
else
    echo "❌ 并发处理测试失败"
fi
echo "=========================================="

exit $TEST_RESULT
