#!/usr/bin/env python3
"""
阿里云视频分析平台 - 主程序入口
支持双输入源、ffmpeg场景检测、阿里云服务集成
"""
import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('aliyun_video_analysis.log')
    ]
)

logger = logging.getLogger(__name__)


def load_environment():
    """加载环境变量"""
    try:
        from dotenv import load_dotenv
        
        # 尝试加载 .env 文件
        env_file = project_root / '.env'
        if env_file.exists():
            load_dotenv(env_file)
            logger.info("已加载 .env 文件")
        else:
            logger.warning("未找到 .env 文件，请参考 .env.aliyun.example 创建配置文件")
            
    except ImportError:
        logger.info("python-dotenv 未安装，跳过 .env 文件加载")


def check_dependencies():
    """检查必要的依赖"""
    required_packages = [
        'gradio',
        'oss2', 
        'asyncio',
        'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.error(f"缺少必要依赖: {missing_packages}")
        logger.error("请运行: pip install -r requirements_aliyun.txt")
        return False
    
    return True


def check_system_requirements():
    """检查系统要求"""
    # 检查 ffmpeg
    import subprocess
    
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("✅ ffmpeg 已安装")
        else:
            logger.warning("❌ ffmpeg 未正确安装")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("❌ ffmpeg 未安装或不在 PATH 中")
        return False
    
    # 检查 yt-dlp
    try:
        result = subprocess.run(['yt-dlp', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("✅ yt-dlp 已安装")
        else:
            logger.warning("❌ yt-dlp 未正确安装")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("❌ yt-dlp 未安装或不在 PATH 中")
        return False
    
    return True


def main():
    """主程序入口"""
    logger.info("🚀 启动阿里云视频分析平台...")
    
    # 加载环境变量
    load_environment()
    
    # 检查依赖
    if not check_dependencies():
        logger.error("❌ 依赖检查失败，程序退出")
        sys.exit(1)
    
    # 检查系统要求
    if not check_system_requirements():
        logger.error("❌ 系统要求检查失败")
        logger.error("请确保已安装 ffmpeg 和 yt-dlp")
        logger.error("安装指令:")
        logger.error("  macOS: brew install ffmpeg yt-dlp")
        logger.error("  Ubuntu: apt install ffmpeg && pip install yt-dlp")
        logger.error("  Windows: 请下载并安装 ffmpeg，然后 pip install yt-dlp")
        sys.exit(1)
    
    # 检查配置
    required_env_vars = [
        'ALIYUN_ACCESS_KEY_ID',
        'ALIYUN_ACCESS_KEY_SECRET', 
        'ALIYUN_OSS_ENDPOINT',
        'ALIYUN_OSS_BUCKET',
        'OPENAI_API_KEY'
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"⚠️  缺少环境变量: {missing_vars}")
        logger.warning("部分服务可能不可用，请检查配置")
        logger.warning("参考 .env.openai.example 文件进行配置")
    else:
        logger.info("✅ 配置检查通过")
    
    try:
        # 导入并启动Gradio应用
        from aliyun_gradio_app import create_aliyun_video_analysis_interface
        
        logger.info("🌐 创建Web界面...")
        demo = create_aliyun_video_analysis_interface()
        
        # 获取端口配置
        port = int(os.getenv('APP_PORT', 7860))
        
        logger.info(f"🎬 阿里云视频分析平台启动成功!")
        logger.info(f"🔗 访问地址: http://localhost:{port}")
        logger.info("🛑 按 Ctrl+C 停止服务")
        
        # 启动服务
        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
            share=False,
            show_error=True,
            inbrowser=True,
            quiet=False
        )
        
    except KeyboardInterrupt:
        logger.info("👋 用户停止服务")
    except Exception as e:
        logger.exception(f"❌ 程序运行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()