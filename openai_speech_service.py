"""
OpenAI Whisper语音识别服务
替代阿里云语音服务，提供更简单可靠的音频转录功能
支持段落级时间戳和多语言识别
"""
import logging
import os
import time
import requests
import asyncio
import tempfile
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """转录段落"""
    text: str
    start_time: float
    end_time: float
    confidence: float


@dataclass
class TranscriptionResult:
    """转录结果"""
    segments: List[TranscriptSegment]
    language: str
    confidence: float
    audio_oss_url: str


class OpenAISpeechService:
    """OpenAI Whisper语音识别服务"""
    
    def __init__(self):
        """初始化OpenAI语音服务"""
        # 从环境变量获取OpenAI API密钥
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = "https://api.openai.com/v1"
        
        # 检查API密钥
        if not self.api_key:
            logger.warning("OpenAI API密钥未设置，请设置环境变量：OPENAI_API_KEY")
            self.available = False
        else:
            self.available = True
            logger.info("OpenAI Whisper语音服务初始化成功")
    
    def is_available(self) -> bool:
        """检查语音服务是否可用"""
        return self.available and bool(self.api_key)
    
    async def transcribe_audio_with_timestamps(self, audio_path: str, language: str = "zh") -> Optional[Dict[str, Any]]:
        """
        使用OpenAI Whisper API转录音频并获取详细时间戳
        
        Args:
            audio_path: 音频文件路径
            language: 语言代码 (zh, en, auto等)
            
        Returns:
            包含详细时间戳的转录结果
        """
        if not self.is_available():
            logger.error("OpenAI语音服务不可用")
            return None
        
        if not os.path.exists(audio_path):
            logger.error(f"音频文件不存在: {audio_path}")
            return None
        
        try:
            logger.info(f"开始转录音频文件: {audio_path}")
            
            # 准备API请求
            url = f"{self.api_base}/audio/transcriptions"
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # 准备文件和数据
            with open(audio_path, "rb") as audio_file:
                files = {
                    "file": (os.path.basename(audio_path), audio_file, "audio/mpeg")
                }
                
                data = {
                    "model": "whisper-1",
                    "response_format": "verbose_json",  # 获取详细信息包括时间戳
                    "timestamp_granularities": ["word", "segment"]  # 词级和段落级时间戳
                }
                
                # 设置语言（如果指定且不是auto）
                if language and language != "auto":
                    language_map = {
                        "zh": "zh",
                        "en": "en", 
                        "es": "es",
                        "fr": "fr",
                        "de": "de",
                        "ja": "ja",
                        "ko": "ko"
                    }
                    if language in language_map:
                        data["language"] = language_map[language]
                
                logger.info("发送转录请求到OpenAI...")
                
                # 创建异步请求
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, 
                    lambda: requests.post(url, headers=headers, files=files, data=data, timeout=300)
                )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"转录成功，语言: {result.get('language', 'unknown')}")
                return result
            else:
                error_msg = f"OpenAI API错误: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return None
                
        except Exception as e:
            logger.exception(f"转录过程中发生错误: {e}")
            return None
    
    def _parse_transcription_to_segments(self, transcription_data: Dict[str, Any], audio_oss_url: str) -> Optional[TranscriptionResult]:
        """
        将OpenAI Whisper结果解析为段落级时间戳
        
        Args:
            transcription_data: OpenAI API返回的数据
            audio_oss_url: 音频的OSS URL
            
        Returns:
            解析后的转录结果
        """
        try:
            # 获取基本信息
            language = transcription_data.get("language", "zh")
            full_text = transcription_data.get("text", "")
            
            # 获取段落信息（segments）
            segments_data = transcription_data.get("segments", [])
            
            if not segments_data:
                logger.warning("没有找到段落级时间戳数据")
                # 如果没有段落数据，创建一个包含全文的段落
                segments = [TranscriptSegment(
                    text=full_text,
                    start_time=0.0,
                    end_time=0.0,
                    confidence=0.8
                )]
            else:
                segments = []
                
                for segment in segments_data:
                    # 获取段落信息
                    text = segment.get("text", "").strip()
                    start_time = segment.get("start", 0.0)
                    end_time = segment.get("end", 0.0)
                    
                    # 计算置信度（OpenAI可能不提供，使用默认值）
                    confidence = segment.get("avg_logprob", 0.0)
                    # 将logprob转换为0-1的置信度
                    if confidence < 0:
                        confidence = max(0.0, 1.0 + confidence / 5.0)  # 简单的转换
                    else:
                        confidence = min(1.0, confidence)
                    
                    if text:  # 只添加非空文本的段落
                        segment_obj = TranscriptSegment(
                            text=text,
                            start_time=start_time,
                            end_time=end_time,
                            confidence=confidence
                        )
                        segments.append(segment_obj)
            
            # 计算总体置信度
            if segments:
                overall_confidence = sum(seg.confidence for seg in segments) / len(segments)
            else:
                overall_confidence = 0.0
            
            result = TranscriptionResult(
                segments=segments,
                language=language,
                confidence=overall_confidence,
                audio_oss_url=audio_oss_url
            )
            
            logger.info(f"解析完成，共{len(segments)}个段落，总体置信度: {overall_confidence:.2f}")
            return result
            
        except Exception as e:
            logger.exception(f"解析转录结果失败: {e}")
            return None
    
    async def extract_and_transcribe_audio(self, video_path: str, video_id: str) -> Optional[TranscriptionResult]:
        """
        从视频中提取音频并转录
        
        Args:
            video_path: 视频文件路径
            video_id: 视频唯一标识
            
        Returns:
            转录结果
        """
        try:
            # 使用ffmpeg提取音频
            audio_path = await self._extract_audio_with_ffmpeg(video_path, video_id)
            
            if not audio_path:
                logger.error("音频提取失败")
                return None
            
            # 上传音频到OSS（如果OSS服务可用）
            audio_oss_url = ""
            try:
                from aliyun_oss_service import oss_service
                if oss_service.is_available():
                    audio_oss_url = await oss_service.upload_audio(audio_path, video_id)
                    logger.info(f"音频已上传到OSS: {audio_oss_url}")
                else:
                    logger.warning("OSS服务不可用，音频文件将保留在本地")
                    audio_oss_url = f"local://{audio_path}"
            except Exception as e:
                logger.warning(f"OSS上传失败，使用本地路径: {e}")
                audio_oss_url = f"local://{audio_path}"
            
            # 转录音频
            transcription_data = await self.transcribe_audio_with_timestamps(audio_path)
            
            if not transcription_data:
                logger.error("音频转录失败")
                return None
            
            # 解析转录结果
            result = self._parse_transcription_to_segments(transcription_data, audio_oss_url)
            
            # 清理本地音频文件（如果已上传到OSS）
            if audio_oss_url.startswith("http") and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.debug(f"已清理本地音频文件: {audio_path}")
                except Exception as e:
                    logger.warning(f"清理本地音频文件失败: {e}")
            
            return result
            
        except Exception as e:
            logger.exception(f"音频提取和转录失败: {e}")
            return None
    
    async def _extract_audio_with_ffmpeg(self, video_path: str, video_id: str) -> Optional[str]:
        """使用ffmpeg提取音频"""
        try:
            # 生成临时音频文件路径
            temp_dir = tempfile.gettempdir()
            audio_path = os.path.join(temp_dir, f"{video_id}_audio.mp3")
            
            # ffmpeg命令 - 针对Whisper优化
            cmd = [
                'ffmpeg', '-i', video_path,
                '-q:a', '0',        # 高质量音频
                '-map', 'a',        # 只提取音频
                '-ar', '16000',     # 16kHz采样率（Whisper推荐）
                '-ac', '1',         # 单声道
                '-f', 'mp3',        # MP3格式
                audio_path, '-y'    # 覆盖输出文件
            ]
            
            logger.info(f"使用ffmpeg提取音频: {video_path} -> {audio_path}")
            
            # 执行ffmpeg命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_path):
                logger.info(f"音频提取成功: {audio_path}")
                return audio_path
            else:
                logger.error(f"ffmpeg提取音频失败: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.exception(f"ffmpeg音频提取异常: {e}")
            return None
    
    async def transcribe_file(self, audio_url: str, language: str = "zh") -> Optional[TranscriptionResult]:
        """
        直接转录音频文件（兼容阿里云服务接口）
        
        Args:
            audio_url: 音频文件URL或本地路径
            language: 语言代码
            
        Returns:
            转录结果
        """
        try:
            # 如果是OSS URL，需要先下载
            if audio_url.startswith("http"):
                # 下载音频文件到本地
                temp_dir = tempfile.gettempdir()
                audio_path = os.path.join(temp_dir, f"temp_audio_{int(time.time())}.mp3")
                
                response = requests.get(audio_url, timeout=120)
                if response.status_code == 200:
                    with open(audio_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"已下载音频文件: {audio_url} -> {audio_path}")
                else:
                    logger.error(f"下载音频失败: {response.status_code}")
                    return None
            elif audio_url.startswith("local://"):
                audio_path = audio_url.replace("local://", "")
            else:
                audio_path = audio_url
            
            # 转录音频
            transcription_data = await self.transcribe_audio_with_timestamps(audio_path, language)
            
            if not transcription_data:
                return None
            
            # 解析结果
            result = self._parse_transcription_to_segments(transcription_data, audio_url)
            
            # 清理临时文件
            if audio_url.startswith("http") and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass
            
            return result
            
        except Exception as e:
            logger.exception(f"音频文件转录失败: {e}")
            return None


# 创建单例实例
speech_service = OpenAISpeechService()