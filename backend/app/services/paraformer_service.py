"""
阿里云 Paraformer-v2 语音识别服务
使用阿里云 DashScope SDK 的 Paraformer 模型进行音频转录
支持说话人分离、高精度时间戳、更好的分句效果
"""
import logging
import os
import asyncio
import tempfile
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# 确保加载 .env 文件
project_root = Path(__file__).parent.parent.parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file, override=True)
else:
    backend_env = project_root / "backend" / ".env"
    if backend_env.exists():
        load_dotenv(backend_env, override=True)

import dashscope
from dashscope.audio.asr import Transcription

from ..core.logging import logger
from ..models.analysis import TranscriptSegment, TranscriptMetadata


@dataclass
class TranscriptionResult:
    """转录结果"""
    segments: List[TranscriptSegment]
    language: str
    confidence: float
    audio_oss_url: str
    full_text: str = ""  # 完整文本
    speaker_count: int = 0  # 说话人数量


class ParaformerSpeechService:
    """阿里云 Paraformer-v2 语音识别服务"""
    
    def __init__(self):
        """初始化阿里云 Paraformer 语音服务"""
        # 从环境变量获取阿里云 DashScope API密钥
        # 优先使用 TRANSCRIPT_SERVICE_API_KEY (专用于音频转录服务)
        # 后备选项: QWEN_API_KEY 或 DASHSCOPE_API_KEY
        self.api_key = (
            os.getenv("TRANSCRIPT_SERVICE_API_KEY") or 
            os.getenv("QWEN_API_KEY") or 
            os.getenv("DASHSCOPE_API_KEY")
        )
        
        # 同时设置两种方式的API密钥
        if self.api_key:
            # 方式1: 设置环境变量 (某些API调用会使用)
            os.environ["DASHSCOPE_API_KEY"] = self.api_key
            # 方式2: 直接设置dashscope.api_key (推荐方式)
            dashscope.api_key = self.api_key
            logger.info("使用音频转录服务API密钥初始化 Paraformer")
        
        # 检查API密钥
        if not self.api_key:
            logger.warning("阿里云 DashScope API密钥未设置,请设置环境变量: TRANSCRIPT_SERVICE_API_KEY, QWEN_API_KEY 或 DASHSCOPE_API_KEY")
            self.available = False
        else:
            self.available = True
            logger.info("阿里云 Paraformer-v2 语音服务初始化成功")
    
    def is_available(self) -> bool:
        """检查语音服务是否可用"""
        return self.available and bool(self.api_key)
    
    async def transcribe_audio_with_timestamps(
        self, 
        audio_oss_url: str, 
        language: str = "auto",
        enable_diarization: bool = True,
        enable_words: bool = True
    ) -> Optional[Any]:
        """
        使用阿里云 Paraformer-v2 API 转录音频并获取详细时间戳
        
        Args:
            audio_oss_url: 音频文件的OSS公共URL
            language: 语言代码 (auto 表示自动检测)
            enable_diarization: 是否启用说话人分离 (默认开启)
            enable_words: 是否启用词级别时间戳 (默认开启)
            
        Returns:
            包含详细时间戳的转录结果
        """
        if not self.is_available():
            logger.error("阿里云 Paraformer 语音服务不可用")
            return None
        
        try:
            logger.info(f"开始转录音频文件: {audio_oss_url}")
            logger.info(f"配置 - 说话人分离: {enable_diarization}, 词级时间戳: {enable_words}")
            
            # 调用 Paraformer-v2 异步转录 API
            # 参考: https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-python-sdk
            logger.info("发送转录请求到阿里云 Paraformer-v2...")
            
            transcribe_response = Transcription.async_call(
                model='paraformer-v2',  # 使用 Paraformer-v2 模型
                file_urls=[audio_oss_url],
                diarization_enabled=enable_diarization,  # 说话人分离 (仅适用于单声道)
                # language_hints 对 Paraformer 是可选的，会自动检测
            )
            
            # 检查响应是否有效
            if not transcribe_response:
                logger.error("转录API调用失败: 返回空响应")
                return None
            
            # 检查响应状态码
            if hasattr(transcribe_response, 'status_code') and transcribe_response.status_code != 200:
                error_msg = f"转录API调用失败: HTTP {transcribe_response.status_code}"
                if hasattr(transcribe_response, 'message'):
                    error_msg += f" - {transcribe_response.message}"
                logger.error(error_msg)
                return None
            
            # 检查output是否存在
            if not hasattr(transcribe_response, 'output') or transcribe_response.output is None:
                logger.error("转录API调用失败: 响应中没有output字段")
                logger.error(f"完整响应: {transcribe_response}")
                return None
            
            # 获取任务ID
            if not hasattr(transcribe_response.output, 'task_id') or not transcribe_response.output.task_id:
                logger.error("转录API调用失败: 没有获取到task_id")
                logger.error(f"完整output: {transcribe_response.output}")
                return None
                
            task_id = transcribe_response.output.task_id
            logger.info(f"转录任务已创建,任务ID: {task_id}")
            
            # 轮询任务状态
            max_wait_time = 300  # 最大等待时间(秒) - Paraformer 可能需要更长时间
            poll_interval = 5  # 轮询间隔(秒)
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                # 等待一段时间后查询
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                
                # 查询任务状态
                transcribe_response = Transcription.fetch(task=task_id)
                task_status = transcribe_response.output.task_status
                
                logger.info(f"任务状态: {task_status} (已等待 {elapsed_time}s)")
                
                if task_status == "SUCCEEDED":
                    logger.info("转录任务成功完成")
                    return transcribe_response.output
                elif task_status == "FAILED":
                    error_msg = f"转录任务失败: {transcribe_response.output}"
                    logger.error(error_msg)
                    return None
            
            # 超时
            logger.error(f"转录任务超时(超过 {max_wait_time}s)")
            return None
                
        except Exception as e:
            logger.exception(f"转录过程中发生错误: {e}")
            return None
    
    def _parse_transcription_to_segments(
        self, 
        transcription_output: Any, 
        audio_oss_url: str
    ) -> Optional[TranscriptionResult]:
        """
        将阿里云 Paraformer-v2 结果解析为段落级时间戳
        
        Paraformer-v2 返回格式:
        {
            "transcripts": [
                {
                    "channel_id": 0,
                    "text": "完整文本",
                    "sentences": [
                        {
                            "begin_time": 100,  # 毫秒
                            "end_time": 3820,
                            "text": "句子文本",
                            "speaker_id": 0,  # 说话人ID (启用分离时)
                            "words": [...]  # 词级别信息
                        }
                    ]
                }
            ]
        }
        
        Args:
            transcription_output: Paraformer API返回的output对象
            audio_oss_url: 音频的OSS URL
            
        Returns:
            解析后的转录结果
        """
        try:
            # 获取转录结果
            results = transcription_output.results
            
            # ========== DEBUG: 打印 Paraformer 返回结果结构 ==========
            logger.info("=" * 80)
            logger.info("Paraformer-v2 转录结果原始数据:")
            logger.info(f"transcription_output 类型: {type(transcription_output)}")
            logger.info(f"results 类型: {type(results)}")
            logger.info(f"results 数量: {len(results) if results else 0}")
            
            if results:
                logger.info(f"results[0] 类型: {type(results[0])}")
                logger.info(f"results[0] 内容预览: {str(results[0])[:500]}")
                if isinstance(results[0], dict):
                    logger.info(f"results[0] 键名: {list(results[0].keys())}")
            logger.info("=" * 80)
            # ========== END DEBUG ==========
            
            if not results:
                logger.warning("没有找到转录结果")
                return None
            
            # 获取第一个文件的转录结果
            result_data = results[0]
            
            # 尝试获取转录URL (用于下载详细JSON)
            transcription_url = result_data.get('transcription_url', '')
            
            segments = []
            full_text = ""
            speaker_ids = set()
            
            # 首先尝试从 transcription_url 下载完整的 JSON 结果
            if transcription_url:
                logger.info(f"从转录URL获取详细结果: {transcription_url}")
                try:
                    import requests
                    response = requests.get(transcription_url, timeout=30)
                    response.raise_for_status()
                    
                    # 解析 JSON 响应
                    transcription_data = response.json()
                    logger.info(f"转录JSON数据结构: {list(transcription_data.keys())}")
                    
                    # Paraformer-v2 标准格式
                    if 'transcripts' in transcription_data:
                        transcripts = transcription_data['transcripts']
                        
                        if transcripts and isinstance(transcripts, list):
                            for transcript in transcripts:
                                channel_id = transcript.get('channel_id', 0)
                                full_text = transcript.get('text', '')
                                sentences = transcript.get('sentences', [])
                                
                                logger.info(f"频道 {channel_id}: {len(sentences)} 个句子")
                                
                                for sentence in sentences:
                                    text = sentence.get('text', '').strip()
                                    begin_time = sentence.get('begin_time', 0) / 1000.0  # 毫秒转秒
                                    end_time = sentence.get('end_time', 0) / 1000.0
                                    speaker_id = sentence.get('speaker_id', 0)  # 说话人ID
                                    
                                    # 记录说话人
                                    speaker_ids.add(speaker_id)
                                    
                                    # Paraformer 没有直接的置信度，使用默认值
                                    confidence = 0.95
                                    
                                    if text:
                                        segment_obj = TranscriptSegment(
                                            text=text,
                                            start_time=begin_time,
                                            end_time=end_time,
                                            confidence=confidence
                                        )
                                        segments.append(segment_obj)
                                        
                                        logger.debug(
                                            f"[说话人{speaker_id}] "
                                            f"{begin_time:.2f}s - {end_time:.2f}s: {text[:50]}..."
                                        )
                    
                    logger.info(f"成功解析 {len(segments)} 个句子段落")
                    logger.info(f"检测到 {len(speaker_ids)} 个说话人: {speaker_ids}")
                    
                except Exception as e:
                    logger.error(f"从转录URL获取详细结果失败: {e}")
                    logger.exception(e)
            
            # 如果从 URL 解析失败，尝试从 result_data 中的 sentences 字段解析
            if not segments:
                logger.info("尝试从 result_data 直接解析句子")
                sentences = result_data.get('sentences', [])
                
                if sentences:
                    for sentence in sentences:
                        text = sentence.get("text", "").strip()
                        begin_time = sentence.get("begin_time", 0) / 1000.0
                        end_time = sentence.get("end_time", 0) / 1000.0
                        speaker_id = sentence.get("speaker_id", 0)
                        confidence = 0.95
                        
                        speaker_ids.add(speaker_id)
                        
                        if text:
                            segment_obj = TranscriptSegment(
                                text=text,
                                start_time=begin_time,
                                end_time=end_time,
                                confidence=confidence
                            )
                            segments.append(segment_obj)
            
            # 如果还是没有段落，创建一个包含完整文本的段落
            if not segments and full_text:
                logger.warning("无法解析句子，使用完整文本创建单个段落")
                segments = [TranscriptSegment(
                    text=full_text,
                    start_time=0.0,
                    end_time=0.0,
                    confidence=0.95
                )]
            
            # 计算总体置信度
            if segments:
                overall_confidence = sum(seg.confidence for seg in segments) / len(segments)
            else:
                overall_confidence = 0.0
            
            # 如果没有完整文本，从段落合并
            if not full_text and segments:
                full_text = ' '.join(seg.text for seg in segments)
            
            result = TranscriptionResult(
                segments=segments,
                language='zh',  # Paraformer 主要用于中文
                confidence=overall_confidence,
                audio_oss_url=audio_oss_url,
                full_text=full_text,
                speaker_count=len(speaker_ids)
            )
            
            logger.info(f"解析完成:")
            logger.info(f"  - 段落数: {len(segments)}")
            logger.info(f"  - 说话人数: {len(speaker_ids)}")
            logger.info(f"  - 总体置信度: {overall_confidence:.2f}")
            logger.info(f"  - 完整文本长度: {len(full_text)} 字符")
            
            return result
            
        except Exception as e:
            logger.exception(f"解析转录结果失败: {e}")
            return None
    
    async def extract_and_transcribe_audio(
        self, 
        video_path: str, 
        video_id: str,
        enable_diarization: bool = True
    ) -> Optional[TranscriptionResult]:
        """
        从视频中提取音频并转录
        
        Args:
            video_path: 视频文件路径
            video_id: 视频唯一标识
            enable_diarization: 是否启用说话人分离
            
        Returns:
            转录结果
        """
        try:
            # 使用ffmpeg提取音频
            audio_path = await self._extract_audio_with_ffmpeg(video_path, video_id)
            
            if not audio_path:
                logger.error("音频提取失败")
                return None
            
            # 必须上传音频到OSS(Paraformer 需要公共URL)
            try:
                from .oss_service import oss_service
                if not oss_service.is_available():
                    logger.error("OSS服务不可用,Paraformer 需要音频的公共URL")
                    return None
                
                audio_oss_url_temp = await oss_service.upload_audio(audio_path, video_id)
                if not audio_oss_url_temp:
                    logger.error("OSS上传返回空URL")
                    return None
                audio_oss_url: str = audio_oss_url_temp
                logger.info(f"音频已上传到OSS: {audio_oss_url}")
                
            except Exception as e:
                logger.error(f"OSS上传失败,无法进行转录: {e}")
                return None
            
            # 转录音频(使用OSS URL)
            transcription_output = await self.transcribe_audio_with_timestamps(
                audio_oss_url,
                enable_diarization=enable_diarization
            )
            
            if not transcription_output:
                logger.error("音频转录失败")
                return None
            
            # 解析转录结果
            result = self._parse_transcription_to_segments(transcription_output, audio_oss_url)
            
            # 清理本地音频文件
            if os.path.exists(audio_path):
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
        """
        使用ffmpeg提取音频,针对 Paraformer 优化
        
        Paraformer 建议:
        - 单声道 (说话人分离仅支持单声道)
        - 16kHz 采样率
        - PCM 16-bit 编码
        """
        try:
            # 生成临时音频文件路径
            temp_dir = tempfile.gettempdir()
            audio_path = os.path.join(temp_dir, f"{video_id}_audio_paraformer.wav")
            
            # ffmpeg命令 - 针对 Paraformer 优化
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn',                      # 不处理视频
                '-acodec', 'pcm_s16le',     # PCM 16-bit 编码
                '-ar', '16000',             # 16kHz采样率
                '-ac', '1',                 # 单声道 (说话人分离要求)
                '-f', 'wav',                # WAV格式
                audio_path, '-y'            # 覆盖输出文件
            ]
            
            logger.info(f"使用ffmpeg提取音频(单声道): {video_path} -> {audio_path}")
            
            # 执行ffmpeg命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_path):
                audio_size = os.path.getsize(audio_path) / (1024 * 1024)  # MB
                logger.info(f"音频提取成功: {audio_path} (大小: {audio_size:.2f}MB)")
                return audio_path
            else:
                logger.error(f"ffmpeg提取音频失败: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.exception(f"ffmpeg音频提取异常: {e}")
            return None
    
    async def transcribe_file(
        self, 
        audio_url: str, 
        language: str = "auto",
        enable_diarization: bool = True
    ) -> Optional[TranscriptionResult]:
        """
        直接转录音频文件(使用 OSS URL)
        
        Args:
            audio_url: 音频文件的 OSS URL
            language: 语言代码 (Paraformer主要支持中文)
            enable_diarization: 是否启用说话人分离
            
        Returns:
            转录结果
        """
        try:
            # Paraformer 需要公共的 OSS URL
            if not audio_url.startswith("http"):
                logger.error(f"Paraformer 需要公共的 OSS URL,当前URL: {audio_url}")
                return None
            
            # 转录音频
            transcription_output = await self.transcribe_audio_with_timestamps(
                audio_url, 
                language,
                enable_diarization=enable_diarization
            )
            
            if not transcription_output:
                return None
            
            # 解析结果
            result = self._parse_transcription_to_segments(transcription_output, audio_url)
            
            return result
            
        except Exception as e:
            logger.exception(f"音频文件转录失败: {e}")
            return None


# 创建单例实例
paraformer_service = ParaformerSpeechService()
