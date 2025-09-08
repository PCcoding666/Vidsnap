#!/usr/bin/env python3
"""
阿里云视频分析平台 - 测试脚本
测试各个服务模块的功能
"""
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_oss_service():
    """测试OSS服务"""
    logger.info("🧪 测试OSS服务...")
    
    try:
        from aliyun_oss_service import oss_service
        
        # 检查服务可用性
        if oss_service.is_available():
            logger.info("✅ OSS服务配置正确")
            return True
        else:
            logger.warning("❌ OSS服务配置不完整")
            return False
            
    except Exception as e:
        logger.error(f"❌ OSS服务测试失败: {e}")
        return False


async def test_speech_service():
    """测试语音服务"""
    logger.info("🧪 测试OpenAI Whisper语音服务...")
    
    try:
        from openai_speech_service import speech_service  # 使用OpenAI语音服务
        
        # 检查服务可用性
        if speech_service.is_available():
            logger.info("✅ OpenAI Whisper语音服务配置正确")
            return True
        else:
            logger.warning("❌ OpenAI语音服务配置不完整")
            return False
            
    except Exception as e:
        logger.error(f"❌ OpenAI语音服务测试失败: {e}")
        return False


async def test_video_service():
    """测试视频服务"""
    logger.info("🧪 测试视频处理服务...")
    
    try:
        from aliyun_video_service import video_service
        
        # 视频服务不需要特殊配置，总是可用
        logger.info("✅ 视频处理服务正常")
        return True
        
    except Exception as e:
        logger.error(f"❌ 视频服务测试失败: {e}")
        return False


async def test_pipeline():
    """测试处理管道"""
    logger.info("🧪 测试视频处理管道...")
    
    try:
        from aliyun_video_pipeline import pipeline
        
        # 检查服务可用性
        status = pipeline.check_services_availability()
        
        logger.info("📊 服务状态:")
        for service, available in status.items():
            icon = "✅" if available else "❌"
            logger.info(f"  {icon} {service}: {'可用' if available else '不可用'}")
        
        # 所有服务至少有一个可用就算测试通过
        any_available = any(status.values())
        if any_available:
            logger.info("✅ 处理管道可以运行")
            return True
        else:
            logger.warning("❌ 所有关键服务都不可用")
            return False
            
    except Exception as e:
        logger.error(f"❌ 处理管道测试失败: {e}")
        return False


async def test_system_dependencies():
    """测试系统依赖"""
    logger.info("🧪 测试系统依赖...")
    
    import subprocess
    
    dependencies = {
        'ffmpeg': ['ffmpeg', '-version'],
        'ffprobe': ['ffprobe', '-version'], 
        'yt-dlp': ['yt-dlp', '--version']
    }
    
    all_available = True
    
    for name, cmd in dependencies.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"✅ {name} 已安装")
            else:
                logger.warning(f"❌ {name} 未正确安装")
                all_available = False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning(f"❌ {name} 未找到")
            all_available = False
    
    return all_available


async def main():
    """主测试函数"""
    logger.info("🚀 开始测试阿里云视频分析平台...")
    
    # 测试列表
    tests = [
        ("系统依赖", test_system_dependencies()),
        ("OSS服务", test_oss_service()),
        ("智能语音服务", test_speech_service()),
        ("视频处理服务", test_video_service()),
        ("处理管道", test_pipeline())
    ]
    
    # 执行测试
    results = {}
    for test_name, test_coro in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"测试: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_coro
            results[test_name] = result
        except Exception as e:
            logger.exception(f"测试 {test_name} 异常: {e}")
            results[test_name] = False
    
    # 测试总结
    logger.info(f"\n{'='*50}")
    logger.info("🏁 测试总结")
    logger.info(f"{'='*50}")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        icon = "✅" if result else "❌"
        logger.info(f"{icon} {test_name}: {'通过' if result else '失败'}")
    
    logger.info(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        logger.info("🎉 所有测试通过！系统可以正常使用")
        return 0
    elif passed >= total // 2:
        logger.warning("⚠️  部分测试失败，系统可以部分使用")
        logger.warning("请检查失败的服务配置")
        return 1
    else:
        logger.error("❌ 大部分测试失败，系统可能无法正常使用")
        logger.error("请检查系统配置和依赖安装")
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)