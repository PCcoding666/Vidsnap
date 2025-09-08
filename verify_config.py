#!/usr/bin/env python3
"""
详细的配置和服务验证脚本
验证所有环境变量和服务配置是否正确
"""
import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_environment():
    """加载环境变量"""
    try:
        from dotenv import load_dotenv
        
        # 尝试加载 .env 文件
        env_file = project_root / '.env'
        if env_file.exists():
            load_dotenv(env_file)
            logger.info(f"✅ 已加载 .env 文件: {env_file}")
            return True
        else:
            logger.error("❌ 未找到 .env 文件")
            return False
            
    except ImportError:
        logger.error("❌ python-dotenv 未安装")
        return False


def check_environment_variables():
    """检查环境变量配置"""
    logger.info("\n🔍 检查环境变量配置...")
    
    # 需要检查的环境变量
    env_vars = {
        "OpenAI配置": {
            "OPENAI_API_KEY": "OpenAI API密钥"
        },
        "阿里云OSS配置": {
            "ALIYUN_ACCESS_KEY_ID": "阿里云访问密钥ID",
            "ALIYUN_ACCESS_KEY_SECRET": "阿里云访问密钥Secret",
            "ALIYUN_OSS_ENDPOINT": "OSS端点",
            "ALIYUN_OSS_BUCKET": "OSS存储桶"
        }
    }
    
    all_configured = True
    
    for category, vars_dict in env_vars.items():
        logger.info(f"\n📋 {category}:")
        for var_name, description in vars_dict.items():
            value = os.getenv(var_name)
            if value:
                # 只显示前几个字符，保护敏感信息
                masked_value = value[:8] + "..." if len(value) > 8 else value
                logger.info(f"  ✅ {var_name}: {masked_value}")
            else:
                logger.error(f"  ❌ {var_name}: 未设置")
                all_configured = False
    
    return all_configured


async def test_openai_connection():
    """测试OpenAI连接"""
    logger.info("\n🧪 测试OpenAI连接...")
    
    try:
        from openai_speech_service import speech_service
        
        if speech_service.is_available():
            # 尝试创建一个简单的API连接测试
            import openai
            
            api_key = os.getenv("OPENAI_API_KEY")
            client = openai.OpenAI(api_key=api_key)
            
            try:
                # 测试API连接（获取模型列表是一个轻量级操作）
                models = client.models.list()
                logger.info("✅ OpenAI API连接成功")
                return True
            except Exception as e:
                logger.error(f"❌ OpenAI API连接失败: {e}")
                return False
        else:
            logger.error("❌ OpenAI语音服务配置不可用")
            return False
            
    except Exception as e:
        logger.error(f"❌ OpenAI服务测试异常: {e}")
        return False


async def test_oss_connection():
    """测试阿里云OSS连接"""
    logger.info("\n🧪 测试阿里云OSS连接...")
    
    try:
        from aliyun_oss_service import oss_service
        
        if oss_service.is_available():
            try:
                # 测试OSS连接（获取bucket信息）
                bucket_name = oss_service.bucket.bucket_name
                bucket_location = oss_service.bucket.get_bucket_location().location
                logger.info(f"✅ OSS连接成功 - 存储桶: {bucket_name}, 区域: {bucket_location}")
                return True
            except Exception as e:
                logger.error(f"❌ OSS连接失败: {e}")
                return False
        else:
            logger.error("❌ OSS服务配置不可用")
            return False
            
    except Exception as e:
        logger.error(f"❌ OSS服务测试异常: {e}")
        return False


async def test_video_processing():
    """测试视频处理功能"""
    logger.info("\n🧪 测试视频处理功能...")
    
    try:
        from aliyun_video_service import video_service
        from aliyun_video_pipeline import pipeline
        
        # 检查管道状态
        status = pipeline.check_services_availability()
        
        logger.info("📊 服务状态检查:")
        for service, available in status.items():
            icon = "✅" if available else "❌"
            service_names = {
                "video_service": "视频处理服务",
                "speech_service": "语音识别服务",
                "oss_service": "OSS存储服务"
            }
            logger.info(f"  {icon} {service_names.get(service, service)}: {'可用' if available else '不可用'}")
        
        # 如果至少有视频服务可用，系统就可以基本运行
        if status.get("video_service", False):
            logger.info("✅ 视频处理核心功能可用")
            return True
        else:
            logger.error("❌ 视频处理核心功能不可用")
            return False
            
    except Exception as e:
        logger.error(f"❌ 视频处理测试异常: {e}")
        return False


async def main():
    """主验证函数"""
    logger.info("🚀 开始详细验证系统配置和服务可行性...")
    
    # 1. 加载环境变量
    env_loaded = load_environment()
    if not env_loaded:
        logger.error("❌ 环境变量加载失败，请检查 .env 文件")
        return False
    
    # 2. 检查环境变量配置
    env_configured = check_environment_variables()
    
    # 3. 测试各项服务
    tests = [
        ("OpenAI连接", test_openai_connection()),
        ("OSS连接", test_oss_connection()),
        ("视频处理", test_video_processing())
    ]
    
    results = {}
    for test_name, test_coro in tests:
        try:
            result = await test_coro
            results[test_name] = result
        except Exception as e:
            logger.error(f"❌ {test_name}测试异常: {e}")
            results[test_name] = False
    
    # 4. 生成总结报告
    logger.info("\n" + "="*60)
    logger.info("🏁 验证总结报告")
    logger.info("="*60)
    
    logger.info(f"📋 环境变量配置: {'✅ 完整' if env_configured else '❌ 不完整'}")
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    for test_name, result in results.items():
        icon = "✅" if result else "❌"
        logger.info(f"🧪 {test_name}: {icon} {'通过' if result else '失败'}")
    
    logger.info(f"\n📊 测试结果: {passed_tests}/{total_tests} 通过")
    
    # 5. 给出建议
    if env_configured and passed_tests >= 2:
        logger.info("🎉 系统配置正确，可以正常使用！")
        logger.info("💡 建议:")
        logger.info("   - 运行 'python main.py' 启动应用")
        logger.info("   - 访问 http://localhost:7860 使用Web界面")
        return True
    elif passed_tests >= 1:
        logger.warning("⚠️  系统可以部分使用，但建议完善配置")
        logger.warning("💡 建议:")
        if not results.get("OpenAI连接", False):
            logger.warning("   - 检查 OPENAI_API_KEY 是否正确")
        if not results.get("OSS连接", False):
            logger.warning("   - 检查阿里云OSS配置是否正确")
        return True
    else:
        logger.error("❌ 系统配置存在重大问题，请检查配置")
        logger.error("💡 建议:")
        logger.error("   - 重新检查 .env 文件中的配置")
        logger.error("   - 确认API密钥有效性")
        return False


if __name__ == "__main__":
    import asyncio
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)