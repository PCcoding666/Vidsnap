#!/usr/bin/env python3
"""
视频处理功能测试
使用一个YouTube视频来测试完整的处理流程
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_youtube_processing():
    """测试YouTube视频处理流程"""
    logger.info("🧪 开始测试YouTube视频处理流程...")
    
    try:
        # 加载环境变量
        from dotenv import load_dotenv
        load_dotenv()
        
        # 导入处理管道
        from aliyun_video_pipeline import pipeline
        
        # 使用一个短视频进行测试（YouTube官方测试视频）
        test_youtube_url = "https://www.youtube.com/watch?v=ScMzIvxBSi4"  # YouTube官方测试视频，约11秒
        
        logger.info(f"📺 测试视频URL: {test_youtube_url}")
        
        # 定义进度回调函数
        def progress_callback(message):
            logger.info(f"📊 处理进度: {message}")
        
        # 执行处理流程
        logger.info("🚀 开始处理视频...")
        result = await pipeline.process_video(
            youtube_url=test_youtube_url,
            progress_callback=progress_callback
        )
        
        # 检查结果
        if result["status"] == "success":
            logger.info("✅ 视频处理成功！")
            
            metadata = result["metadata"]
            logger.info(f"📋 视频信息:")
            logger.info(f"   - 视频ID: {metadata.video_info.video_id}")
            logger.info(f"   - 标题: {metadata.video_info.title}")
            logger.info(f"   - 时长: {metadata.video_info.duration}秒")
            logger.info(f"   - 关键帧数量: {len(metadata.keyframes)}")
            logger.info(f"   - 转录段落数量: {len(metadata.transcript.segments)}")
            
            logger.info(f"🖼️  关键帧信息:")
            for i, keyframe in enumerate(metadata.keyframes[:3]):  # 只显示前3个
                logger.info(f"   - 帧{keyframe.frame_id}: {keyframe.timestamp:.1f}s - {keyframe.oss_image_url}")
            
            logger.info(f"📝 转录内容预览:")
            for i, segment in enumerate(metadata.transcript.segments[:2]):  # 只显示前2个段落
                logger.info(f"   - 段落{i+1} ({segment.start_time:.1f}s-{segment.end_time:.1f}s): {segment.text[:50]}...")
            
            logger.info("🎉 完整的视频处理流程测试成功！")
            return True
        else:
            logger.error(f"❌ 视频处理失败: {result.get('error', '未知错误')}")
            return False
            
    except Exception as e:
        logger.exception(f"❌ 测试过程中发生异常: {e}")
        return False


async def test_local_video_processing():
    """测试本地视频文件处理（如果有的话）"""
    logger.info("🧪 检查本地测试视频...")
    
    # 检查是否有本地测试视频
    test_video_paths = [
        "/Users/chengpeng/Downloads/test_video.mp4",
        "./test_video.mp4",
        "./sample.mp4"
    ]
    
    local_video = None
    for path in test_video_paths:
        if os.path.exists(path):
            local_video = path
            break
    
    if not local_video:
        logger.info("📁 未找到本地测试视频，跳过本地视频测试")
        return True
    
    try:
        logger.info(f"📹 测试本地视频: {local_video}")
        
        from aliyun_video_pipeline import pipeline
        
        def progress_callback(message):
            logger.info(f"📊 处理进度: {message}")
        
        result = await pipeline.process_video(
            video_file=local_video,
            progress_callback=progress_callback
        )
        
        if result["status"] == "success":
            logger.info("✅ 本地视频处理成功！")
            return True
        else:
            logger.error(f"❌ 本地视频处理失败: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.exception(f"❌ 本地视频测试异常: {e}")
        return False


async def main():
    """主测试函数"""
    logger.info("🎬 开始视频处理功能验证测试...")
    
    # 测试列表
    tests = [
        ("YouTube视频处理", test_youtube_processing()),
        ("本地视频处理", test_local_video_processing())
    ]
    
    results = {}
    
    for test_name, test_coro in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"🧪 测试: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_coro
            results[test_name] = result
        except Exception as e:
            logger.exception(f"❌ {test_name}测试异常: {e}")
            results[test_name] = False
    
    # 生成测试报告
    logger.info(f"\n{'='*60}")
    logger.info("🏁 视频处理功能测试报告")
    logger.info(f"{'='*60}")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        icon = "✅" if result else "❌"
        logger.info(f"{icon} {test_name}: {'通过' if result else '失败'}")
    
    logger.info(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed > 0:
        logger.info("🎉 视频处理核心功能正常工作！")
        logger.info("💡 您现在可以:")
        logger.info("   1. 通过Web界面 http://localhost:7860 使用完整功能")
        logger.info("   2. 上传视频文件或输入YouTube URL进行处理")
        logger.info("   3. 查看关键帧和音频转录结果")
        return True
    else:
        logger.error("❌ 视频处理功能存在问题，请检查配置")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)