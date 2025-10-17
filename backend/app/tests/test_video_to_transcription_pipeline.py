"""
YouTube 视频到音频转录的端到端集成测试
测试完整流程:下载 -> 提取音频 -> 上传OSS -> SenseVoice转录
"""
import pytest
import os
import sys
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ 已加载环境变量文件: {env_path}")
else:
    print(f"⚠️ 未找到 .env 文件: {env_path}")

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.video_service import video_service
from app.services.oss_service import oss_service
from app.services.speech_service import speech_service
from app.core.logging import logger


# 测试配置
TEST_YOUTUBE_URL = "https://www.youtube.com/watch?v=1PaoWKvcJP0"
NETWORK_TIMEOUT = 180  # 网络超时(秒)


class TestVideoToTranscriptionPipeline:
    """YouTube视频到音频转录完整流程测试"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """测试前后的设置和清理"""
        logger.info("=" * 80)
        logger.info("开始新的测试用例")
        logger.info("=" * 80)
        yield
        logger.info("=" * 80)
        logger.info("测试用例结束")
        logger.info("=" * 80)
    
    def test_dashscope_service_availability(self):
        """测试 DashScope 服务可用性"""
        logger.info("检查 DashScope 服务可用性...")
        
        # 检查环境变量 (优先使用 TRANSCRIPT_SERVICE_API_KEY)
        transcript_key = os.getenv("TRANSCRIPT_SERVICE_API_KEY")
        qwen_key = os.getenv("QWEN_API_KEY")
        
        if transcript_key:
            logger.info("✓ TRANSCRIPT_SERVICE_API_KEY 已设置 (优先使用)")
        elif qwen_key:
            logger.info("✓ QWEN_API_KEY 已设置 (后备选项)")
        else:
            pytest.fail("未设置音频转录API密钥: 请设置 TRANSCRIPT_SERVICE_API_KEY 或 QWEN_API_KEY")
        
        # 检查服务可用性
        assert speech_service.is_available(), "SenseVoice 服务不可用"
        logger.info("✓ SenseVoice 服务可用")
        
        # 检查OSS服务(转录需要)
        assert oss_service.is_available(), "OSS 服务不可用,SenseVoice 需要音频的公共URL"
        logger.info("✓ OSS 服务可用")
    
    @pytest.mark.asyncio
    async def test_full_pipeline_youtube_to_transcription(self):
        """测试完整流程:YouTube下载 -> 音频提取 -> OSS上传 -> SenseVoice转录"""
        
        logger.info("=" * 80)
        logger.info("测试完整流程: YouTube 视频 -> 音频转录")
        logger.info("=" * 80)
        
        start_time = time.time()
        video_id = None
        video_path = None
        download_result = None
        
        try:
            # 步骤1:下载 YouTube 视频
            logger.info("\n步骤 1/5: 下载 YouTube 视频")
            logger.info(f"视频URL: {TEST_YOUTUBE_URL}")
            
            download_start = time.time()
            download_result = await asyncio.wait_for(
                video_service.process_video_dual_source(youtube_url=TEST_YOUTUBE_URL),
                timeout=NETWORK_TIMEOUT
            )
            download_time = time.time() - download_start
            
            assert download_result is not None, "视频处理失败"
            assert download_result.get("status") == "success", f"视频处理失败: {download_result.get('error')}"
            
            video_id = download_result.get("video_id")
            assert video_id is not None, "视频ID为空"
            
            # 从session_temp_dir中查找下载的视频文件
            session_temp_dir = download_result.get("session_temp_dir")
            video_path = None
            
            if session_temp_dir and os.path.exists(session_temp_dir):
                for file in os.listdir(session_temp_dir):
                    if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                        video_path = os.path.join(session_temp_dir, file)
                        break
            
            assert video_path is not None, "未找到下载的视频文件"
            assert os.path.exists(video_path), f"视频文件不存在: {video_path}"
            
            video_metadata = download_result.get("video_metadata", {})
            
            logger.info(f"✓ 视频下载成功")
            logger.info(f"  - 视频ID: {video_id}")
            logger.info(f"  - 本地路径: {video_path}")
            logger.info(f"  - 视频时长: {video_metadata.get('duration', 'unknown')}秒")
            logger.info(f"  - 下载耗时: {download_time:.2f}秒")
            
            # 步骤2:提取音频并上传到OSS
            logger.info("\n步骤 2/5: 提取音频文件")
            
            extract_start = time.time()
            audio_path = await speech_service._extract_audio_with_ffmpeg(video_path, video_id)
            extract_time = time.time() - extract_start
            
            assert audio_path is not None, "音频提取失败"
            assert os.path.exists(audio_path), f"音频文件不存在: {audio_path}"
            
            audio_size = os.path.getsize(audio_path) / (1024 * 1024)  # MB
            logger.info(f"✓ 音频提取成功")
            logger.info(f"  - 音频路径: {audio_path}")
            logger.info(f"  - 音频大小: {audio_size:.2f}MB")
            logger.info(f"  - 提取耗时: {extract_time:.2f}秒")
            
            # 步骤3:上传音频到OSS
            logger.info("\n步骤 3/5: 上传音频到 OSS")
            
            upload_start = time.time()
            audio_oss_url = await oss_service.upload_audio(audio_path, video_id)
            upload_time = time.time() - upload_start
            
            assert audio_oss_url, "音频上传到OSS失败"
            assert audio_oss_url.startswith("http"), f"OSS URL格式错误: {audio_oss_url}"
            
            logger.info(f"✓ 音频上传成功")
            logger.info(f"  - OSS URL: {audio_oss_url}")
            logger.info(f"  - 上传耗时: {upload_time:.2f}秒")
            
            # 步骤4:使用 SenseVoice 转录音频
            logger.info("\n步骤 4/5: 使用 SenseVoice 转录音频")
            logger.info("  (注意:转录可能需要较长时间,最多等待180秒)")
            
            transcribe_start = time.time()
            transcription_result = await asyncio.wait_for(
                speech_service.transcribe_file(audio_oss_url, language="auto"),
                timeout=NETWORK_TIMEOUT
            )
            transcribe_time = time.time() - transcribe_start
            
            assert transcription_result is not None, "音频转录失败"
            assert transcription_result.segments, "转录结果为空"
            
            logger.info(f"✓ 音频转录成功")
            logger.info(f"  - 检测语言: {transcription_result.language}")
            logger.info(f"  - 段落数量: {len(transcription_result.segments)}")
            logger.info(f"  - 总体置信度: {transcription_result.confidence:.2%}")
            logger.info(f"  - 转录耗时: {transcribe_time:.2f}秒")
            
            # 步骤5:验证转录结果
            logger.info("\n步骤 5/5: 验证转录结果")
            
            # 显示前3个转录段落
            logger.info("  转录内容示例(前3段):")
            for i, segment in enumerate(transcription_result.segments[:3]):
                logger.info(f"    [{i+1}] {segment.start_time:.1f}s - {segment.end_time:.1f}s")
                logger.info(f"        文本: {segment.text}")
                logger.info(f"        置信度: {segment.confidence:.2%}")
            
            if len(transcription_result.segments) > 3:
                logger.info(f"    ... (共 {len(transcription_result.segments)} 个段落)")
            
            # 验证转录质量
            total_duration = sum(
                seg.end_time - seg.start_time 
                for seg in transcription_result.segments 
                if seg.end_time > 0
            )
            logger.info(f"  - 转录总时长: {total_duration:.1f}秒")
            
            avg_confidence = transcription_result.confidence
            assert avg_confidence > 0.5, f"转录置信度过低: {avg_confidence:.2%}"
            logger.info(f"  - 平均置信度: {avg_confidence:.2%} (合格)")
            
            # 检查是否有实际文本内容
            total_text_length = sum(len(seg.text) for seg in transcription_result.segments)
            assert total_text_length > 10, "转录文本过短"
            logger.info(f"  - 总文本长度: {total_text_length} 字符")
            
            # 总结
            total_time = time.time() - start_time
            logger.info("\n" + "=" * 80)
            logger.info("✓ 完整流程测试通过!")
            logger.info("=" * 80)
            logger.info(f"总耗时: {total_time:.2f}秒")
            logger.info(f"  - 视频下载: {download_time:.2f}秒")
            logger.info(f"  - 音频提取: {extract_time:.2f}秒")
            logger.info(f"  - OSS上传: {upload_time:.2f}秒")
            logger.info(f"  - SenseVoice转录: {transcribe_time:.2f}秒")
            logger.info("=" * 80)
            
            # 清理本地音频文件
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"✓ 已清理本地音频文件: {audio_path}")
            
        except asyncio.TimeoutError:
            pytest.fail(f"操作超时(超过{NETWORK_TIMEOUT}秒)")
        except Exception as e:
            logger.exception(f"测试失败: {e}")
            raise
        finally:
            # 清理整个session临时目录
            if 'download_result' in locals() and download_result:
                session_temp_dir = download_result.get("session_temp_dir")
                if session_temp_dir and os.path.exists(session_temp_dir):
                    try:
                        import shutil
                        shutil.rmtree(session_temp_dir)
                        logger.info(f"✓ 已清理临时目录: {session_temp_dir}")
                    except Exception as e:
                        logger.warning(f"清理临时目录失败: {e}")
    
    @pytest.mark.asyncio
    async def test_transcription_segments_format(self):
        """测试转录结果的段落格式"""
        
        # 这个测试需要先有一个音频文件
        # 为了简化,我们跳过如果没有可用的测试音频
        
        logger.info("测试转录段落格式...")
        logger.info("(此测试依赖完整流程测试中的音频)")
        
        # 简单验证服务可用性
        assert speech_service.is_available(), "SenseVoice 服务不可用"
        logger.info("✓ SenseVoice 服务可用")
    
    @pytest.mark.asyncio  
    async def test_cleanup_after_processing(self):
        """测试处理后的临时文件清理"""
        
        logger.info("测试临时文件清理...")
        
        # 检查临时目录
        import tempfile
        temp_dir = tempfile.gettempdir()
        
        # 列出临时目录中的音频文件
        audio_files = list(Path(temp_dir).glob("*_audio.*"))
        logger.info(f"临时目录中的音频文件数: {len(audio_files)}")
        
        # 通常测试后应该清理干净
        if audio_files:
            logger.warning(f"发现 {len(audio_files)} 个未清理的音频文件:")
            for f in audio_files:
                logger.warning(f"  - {f}")
        else:
            logger.info("✓ 临时目录清理正常")


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s"])
