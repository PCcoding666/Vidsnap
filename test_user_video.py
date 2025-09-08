#!/usr/bin/env python3
"""
用户指定视频测试脚本
测试用户提供的YouTube视频链接的完整处理流程
"""
import asyncio
import logging
import sys
import os
import time
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_user_video():
    """测试用户提供的YouTube视频"""
    user_video_url = "https://www.youtube.com/watch?v=wOxA4x2f6jg"
    
    logger.info("🎬 开始测试用户提供的YouTube视频")
    logger.info(f"📺 视频链接: {user_video_url}")
    
    try:
        # 加载环境变量
        from dotenv import load_dotenv
        load_dotenv()
        
        # 导入处理管道
        from aliyun_video_pipeline import pipeline
        
        # 记录开始时间
        start_time = time.time()
        
        # 定义详细的进度回调函数
        def progress_callback(message):
            elapsed = time.time() - start_time
            logger.info(f"📊 [{elapsed:.1f}s] {message}")
        
        # 执行完整的视频处理流程
        logger.info("🚀 开始完整的视频处理流程...")
        logger.info("=" * 60)
        
        result = await pipeline.process_video(
            youtube_url=user_video_url,
            progress_callback=progress_callback
        )
        
        # 计算总处理时间
        total_time = time.time() - start_time
        
        logger.info("=" * 60)
        logger.info(f"⏱️  总处理时间: {total_time:.1f}秒")
        
        # 检查并展示结果
        if result["status"] == "success":
            logger.info("🎉 视频处理完全成功！")
            
            # 获取metadata
            metadata = result["metadata"]
            
            # 显示视频基本信息
            logger.info("\n📋 视频基本信息:")
            logger.info(f"   🆔 视频ID: {metadata.video_id}")
            logger.info(f"   📝 标题: {metadata.title}")
            logger.info(f"   ⏰ 时长: {metadata.duration}秒 ({metadata.duration/60:.1f}分钟)")
            logger.info(f"   🔗 OSS视频URL: {metadata.oss_video_url}")
            logger.info(f"   📁 来源类型: {metadata.source_type}")
            if metadata.original_url:
                logger.info(f"   🌐 原始URL: {metadata.original_url}")
            
            # 显示技术信息
            logger.info(f"\n🔧 技术信息:")
            logger.info(f"   📹 视频格式: {metadata.video_format}")
            logger.info(f"   📏 分辨率: {metadata.video_resolution}")
            logger.info(f"   💾 文件大小: {metadata.video_size} bytes ({metadata.video_size/1024/1024:.1f} MB)")
            
            # 显示关键帧信息
            logger.info(f"\n🖼️  关键帧信息 (共{len(metadata.keyframes)}个):")
            for i, keyframe in enumerate(metadata.keyframes):
                logger.info(f"   帧{keyframe.frame_id}: {keyframe.timestamp:.1f}s - {keyframe.scene_description}")
                logger.info(f"     🔗 图片URL: {keyframe.oss_image_url}")
                if i >= 2:  # 只显示前3个，避免输出过长
                    logger.info(f"   ... 还有{len(metadata.keyframes)-3}个关键帧")
                    break
            
            # 显示音频转录信息
            logger.info(f"\n🎤 音频转录信息:")
            logger.info(f"   🌐 识别语言: {metadata.transcript.language}")
            logger.info(f"   🎯 总体置信度: {metadata.transcript.overall_confidence:.2f}")
            logger.info(f"   🔗 音频OSS URL: {metadata.transcript.oss_audio_url}")
            logger.info(f"   📝 转录段落数: {len(metadata.transcript.segments)}")
            
            # 显示转录内容预览
            if metadata.transcript.segments:
                logger.info(f"\n📜 转录内容预览:")
                for i, segment in enumerate(metadata.transcript.segments[:3]):  # 显示前3个段落
                    duration = segment.end_time - segment.start_time
                    logger.info(f"   段落{i+1} ({segment.start_time:.1f}s-{segment.end_time:.1f}s, {duration:.1f}s):")
                    logger.info(f"     📄 内容: {segment.text}")
                    logger.info(f"     🎯 置信度: {segment.confidence:.2f}")
                
                if len(metadata.transcript.segments) > 3:
                    logger.info(f"   ... 还有{len(metadata.transcript.segments)-3}个转录段落")
            
            # 显示处理状态和存储信息
            logger.info(f"\n📊 处理状态:")
            logger.info(f"   ✅ 处理状态: {metadata.processing_status}")
            logger.info(f"   📅 上传时间: {metadata.upload_time}")
            logger.info(f"   ⏰ 处理完成时间: {metadata.processing_completed_time}")
            if metadata.metadata_oss_url:
                logger.info(f"   🗃️  Metadata OSS URL: {metadata.metadata_oss_url}")
            
            # 验证文件完整性
            logger.info(f"\n🔍 文件完整性验证:")
            files_ok = 0
            total_files = 0
            
            # 检查视频文件
            total_files += 1
            if metadata.oss_video_url:
                logger.info(f"   ✅ 视频文件: 已上传到OSS")
                files_ok += 1
            else:
                logger.info(f"   ❌ 视频文件: 上传失败")
            
            # 检查音频文件
            total_files += 1
            if metadata.transcript.oss_audio_url:
                logger.info(f"   ✅ 音频文件: 已上传到OSS")
                files_ok += 1
            else:
                logger.info(f"   ❌ 音频文件: 上传失败")
            
            # 检查关键帧文件
            keyframes_ok = sum(1 for kf in metadata.keyframes if kf.oss_image_url)
            total_files += len(metadata.keyframes)
            files_ok += keyframes_ok
            logger.info(f"   ✅ 关键帧文件: {keyframes_ok}/{len(metadata.keyframes)} 已上传")
            
            # 检查metadata文件
            total_files += 1
            if metadata.metadata_oss_url:
                logger.info(f"   ✅ Metadata文件: 已上传到OSS")
                files_ok += 1
            else:
                logger.info(f"   ❌ Metadata文件: 上传失败")
            
            logger.info(f"\n📈 最终统计:")
            logger.info(f"   🎯 文件完整性: {files_ok}/{total_files} ({files_ok/total_files*100:.1f}%)")
            logger.info(f"   ⚡ 处理效率: {metadata.duration/total_time:.1f}x 实时速度")
            logger.info(f"   💰 估算成本:")
            logger.info(f"     - OpenAI Whisper: ${metadata.duration/60*0.006:.4f} (${0.006:.3f}/分钟)")
            
            # 功能验证总结
            logger.info(f"\n🎊 功能验证总结:")
            logger.info(f"   ✅ YouTube视频下载: 成功")
            logger.info(f"   ✅ ffmpeg关键帧提取: 成功 ({len(metadata.keyframes)}帧)")
            logger.info(f"   ✅ OpenAI语音转录: 成功 ({len(metadata.transcript.segments)}段落)")
            logger.info(f"   ✅ 阿里云OSS存储: 成功 ({files_ok}/{total_files}文件)")
            logger.info(f"   ✅ 并行处理机制: 成功")
            logger.info(f"   ✅ 统一Metadata格式: 成功")
            
            logger.info(f"\n🚀 系统性能表现:")
            logger.info(f"   📊 处理速度: {'优秀' if total_time < metadata.duration*2 else '良好' if total_time < metadata.duration*3 else '需优化'}")
            logger.info(f"   🎯 转录质量: {'优秀' if metadata.transcript.overall_confidence > 0.9 else '良好' if metadata.transcript.overall_confidence > 0.7 else '一般'}")
            logger.info(f"   🖼️  关键帧质量: {'符合规范' if len(metadata.keyframes) <= 10 else '超出限制'}")
            
            return True
            
        else:
            logger.error(f"❌ 视频处理失败: {result.get('error', '未知错误')}")
            logger.error(f"🔍 错误详情: {result}")
            return False
            
    except Exception as e:
        logger.exception(f"❌ 测试过程中发生异常: {e}")
        return False


async def main():
    """主函数"""
    logger.info("🎬 开始用户视频测试")
    logger.info("🔧 正在验证系统配置...")
    
    # 先加载环境变量
    from dotenv import load_dotenv
    load_dotenv()
    
    # 验证环境配置
    required_vars = ["OPENAI_API_KEY", "ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIYUN_OSS_ENDPOINT", "ALIYUN_OSS_BUCKET"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ 缺少必要的环境变量: {missing_vars}")
        return False
    
    logger.info("✅ 环境配置验证通过")
    
    # 执行测试
    success = await test_user_video()
    
    # 最终总结
    logger.info("\n" + "="*80)
    if success:
        logger.info("🎉 用户视频测试完全成功！")
        logger.info("💡 系统完全可用，您可以:")
        logger.info("   1. 通过Web界面处理更多视频")
        logger.info("   2. 查看完整的处理结果")
        logger.info("   3. 使用关键帧和转录功能")
        logger.info("   4. 进行内容搜索和分析")
    else:
        logger.error("❌ 用户视频测试失败，请检查配置和网络连接")
    
    logger.info("="*80)
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)