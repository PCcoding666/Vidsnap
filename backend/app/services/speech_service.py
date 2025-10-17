"""
阿里云 SenseVoice 语音识别服务
使用阿里云 DashScope SDK 的 SenseVoice 模型进行音频转录
支持多语言、带时间戳的高精度转录
"""
import logging
import os
import time
import asyncio
import tempfile
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

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


class SenseVoiceSpeechService:
    """阿里云 SenseVoice 语音识别服务"""
    
    def __init__(self):
        """初始化阿里云 SenseVoice 语音服务"""
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
            logger.info("使用音频转录服务API密钥初始化")
        
        # 检查API密钥
        if not self.api_key:
            logger.warning("阿里云 DashScope API密钥未设置,请设置环境变量: TRANSCRIPT_SERVICE_API_KEY, QWEN_API_KEY 或 DASHSCOPE_API_KEY")
            self.available = False
        else:
            self.available = True
            logger.info("阿里云 SenseVoice 语音服务初始化成功")
    
    def is_available(self) -> bool:
        """检查语音服务是否可用"""
        return self.available and bool(self.api_key)
    
    async def transcribe_audio_with_timestamps(self, audio_oss_url: str, language: str = "auto") -> Optional[Any]:
        """
        使用阿里云 SenseVoice API 转录音频并获取详细时间戳
        
        Args:
            audio_oss_url: 音频文件的OSS公共URL
            language: 语言代码 (zh, en, auto等)
            
        Returns:
            包含详细时间戳的转录结果
        """
        if not self.is_available():
            logger.error("阿里云 SenseVoice 语音服务不可用")
            return None
        
        try:
            logger.info(f"开始转录音频文件: {audio_oss_url}")
            
            # 准备语言提示
            # 重要: SenseVoice 每次只支持识别一种语言,不能在 language_hints 中指定多个语言
            language_hints = []
            if language == "auto":
                # 自动检测默认使用中文
                # SenseVoice 约束: 只能指定一种语言
                language_hints = ["zh"]
            else:
                # 映射语言代码
                language_map = {
                    "zh": "zh",
                    "en": "en",
                    "yue": "yue",  # 粤语
                    "ja": "ja",
                    "ko": "ko",
                    "es": "es",
                    "fr": "fr",
                    "de": "de",
                    "ru": "ru"
                }
                lang_code = language_map.get(language, "zh")
                language_hints = [lang_code]
            
            logger.info(f"语言提示: {language_hints}")
            
            # 调用 SenseVoice 异步转录 API
            logger.info("发送转录请求到阿里云 SenseVoice...")
            transcribe_response = Transcription.async_call(
                model='sensevoice-v1',
                file_urls=[audio_oss_url],
                language_hints=language_hints
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
                # 记录完整响应以便调试
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
            max_wait_time = 180  # 最大等待时间(秒)
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
    
    def _parse_transcription_to_segments(self, transcription_output: Any, audio_oss_url: str) -> Optional[TranscriptionResult]:
        """
        将阿里云 SenseVoice 结果解析为段落级时间戳
        
        Args:
            transcription_output: SenseVoice API返回的output对象
            audio_oss_url: 音频的OSS URL
            
        Returns:
            解析后的转录结果
        """
        try:
            # 获取转录结果
            # transcription_output 是 API 返回的对象，使用属性访问
            results = transcription_output.results
            
            # ========== DEBUG: 打印 SenseVoice 返回结果结构 ==========
            logger.info("=" * 80)
            logger.info("SenseVoice 转录结果原始数据:")
            logger.info(f"transcription_output 类型: {type(transcription_output)}")
            logger.info(f"transcription_output 属性: {dir(transcription_output)}")
            logger.info(f"results 类型: {type(results)}")
            logger.info(f"results 数量: {len(results) if results else 0}")
            
            if results:
                logger.info(f"results[0] 类型: {type(results[0])}")
                logger.info(f"results[0] 内容: {results[0]}")
                if isinstance(results[0], dict):
                    logger.info(f"results[0] 键名: {list(results[0].keys())}")
            logger.info("=" * 80)
            # ========== END DEBUG ==========
            
            if not results:
                logger.warning("没有找到转录结果")
                return None
            
            # 获取第一个文件的转录结果
            # result_data 是字典，使用字典键访问
            result_data = results[0]
            
            # 获取转录的URL和文本 - 使用字典键访问
            transcription_url = result_data.get('transcription_url', '')
            
            # 获取语言信息
            language = result_data.get('language', 'zh')  # 从结果中获取语言，默认中文
            
            # 解析转录文本中的句子
            sentences = result_data.get('sentences', [])
            
            segments = []
            
            if sentences:
                # 如果有句子级别的分段
                for sentence in sentences:
                    text = sentence.get("text", "").strip()
                    begin_time = sentence.get("begin_time", 0) / 1000.0  # 转换为秒
                    end_time = sentence.get("end_time", 0) / 1000.0
                    confidence = sentence.get("confidence", 0.9)  # SenseVoice 置信度
                    
                    if text:
                        segment_obj = TranscriptSegment(
                            text=text,
                            start_time=begin_time,
                            end_time=end_time,
                            confidence=confidence
                        )
                        segments.append(segment_obj)
            else:
                # 如果没有句子分段,需要从 transcription_url 下载 JSON 获取完整文本
                full_text = ""
                
                # SenseVoice 返回的是 transcription_url，需要下载 JSON 文件
                if transcription_url:
                    logger.info(f"从转录URL获取完整文本: {transcription_url}")
                    try:
                        import requests
                        response = requests.get(transcription_url, timeout=30)
                        response.raise_for_status()
                        
                        # 解析 JSON 响应
                        transcription_data = response.json()
                        logger.info(f"转录JSON数据: {transcription_data}")
                        
                        # 提取文本内容
                        # SenseVoice JSON 可能有不同的结构，尝试多种方式
                        if 'transcripts' in transcription_data:
                            # 如果有 transcripts 列表
                            transcripts = transcription_data['transcripts']
                            if transcripts and isinstance(transcripts, list):
                                # 合并所有文本
                                full_text = ' '.join([t.get('text', '') for t in transcripts if 'text' in t])
                        elif 'text' in transcription_data:
                            # 直接有 text 字段
                            full_text = transcription_data['text']
                        elif 'Transcripts' in transcription_data:
                            # 大写版本
                            transcripts = transcription_data['Transcripts']
                            if transcripts and isinstance(transcripts, list):
                                full_text = ' '.join([t.get('Text', t.get('text', '')) for t in transcripts])
                        else:
                            # 尝试直接将整个 JSON 转为字符串（作为后备）
                            logger.warning(f"未找到标准文本字段，JSON结构: {list(transcription_data.keys())}")
                            # 尝试从其他可能的字段提取
                            full_text = str(transcription_data.get('result', transcription_data))
                        
                        if full_text:
                            logger.info(f"成功从 URL 获取转录文本，长度: {len(full_text)} 字符")
                        else:
                            logger.warning("从 URL 获取的转录文本为空")
                            
                    except Exception as e:
                        logger.error(f"从转录URL获取文本失败: {e}")
                        logger.exception(e)
                        full_text = f"(从转录URL获取文本失败: {e})"
                
                if full_text:
                    segments = [TranscriptSegment(
                        text=full_text,
                        start_time=0.0,
                        end_time=0.0,
                        confidence=0.9
                    )]
            
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
            
            logger.info(f"解析完成,共{len(segments)}个段落,总体置信度: {overall_confidence:.2f}")
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
            
            # 必须上传音频到OSS(SenseVoice 需要公共URL)
            audio_oss_url = ""
            try:
                from .oss_service import oss_service
                if not oss_service.is_available():
                    logger.error("OSS服务不可用,SenseVoice 需要音频的公共URL")
                    return None
                
                audio_oss_url = await oss_service.upload_audio(audio_path, video_id)
                logger.info(f"音频已上传到OSS: {audio_oss_url}")
                
            except Exception as e:
                logger.error(f"OSS上传失败,无法进行转录: {e}")
                return None
            
            # 转录音频(使用OSS URL)
            transcription_output = await self.transcribe_audio_with_timestamps(audio_oss_url)
            
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
        """使用ffmpeg提取音频,针对 SenseVoice 优化"""
        try:
            # 生成临时音频文件路径
            temp_dir = tempfile.gettempdir()
            audio_path = os.path.join(temp_dir, f"{video_id}_audio.wav")
            
            # ffmpeg命令 - 针对 SenseVoice 优化
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn',              # 不处理视频
                '-acodec', 'pcm_s16le',  # PCM 16-bit 编码
                '-ar', '16000',     # 16kHz采样率
                '-ac', '1',         # 单声道
                '-f', 'wav',        # WAV格式(SenseVoice 推荐)
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
                audio_size = os.path.getsize(audio_path) / (1024 * 1024)  # MB
                logger.info(f"音频提取成功: {audio_path} (大小: {audio_size:.2f}MB)")
                return audio_path
            else:
                logger.error(f"ffmpeg提取音频失败: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.exception(f"ffmpeg音频提取异常: {e}")
            return None
    
    async def transcribe_file(self, audio_url: str, language: str = "auto") -> Optional[TranscriptionResult]:
        """
        直接转录音频文件(使用 OSS URL)
        
        Args:
            audio_url: 音频文件的 OSS URL
            language: 语言代码
            
        Returns:
            转录结果
        """
        try:
            # SenseVoice 需要公共的 OSS URL
            if not audio_url.startswith("http"):
                logger.error(f"SenseVoice 需要公共的 OSS URL,当前URL: {audio_url}")
                return None
            
            # 转录音频
            transcription_output = await self.transcribe_audio_with_timestamps(audio_url, language)
            
            if not transcription_output:
                return None
            
            # 解析结果
            result = self._parse_transcription_to_segments(transcription_output, audio_url)
            
            return result
            
        except Exception as e:
            logger.exception(f"音频文件转录失败: {e}")
            return None


# 创建单例实例
speech_service = SenseVoiceSpeechService()
