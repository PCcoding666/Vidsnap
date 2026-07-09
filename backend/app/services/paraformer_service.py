"""
阿里云 DashScope 录音文件识别（Transcription）服务。

实际使用的模型由 settings.ASR_MODEL 决定（默认 Fun-ASR-Flash）；类名/文件名沿用
历史 "Paraformer" 命名，仅作为内部实现符号，不代表所调用的模型。
支持分片、重试、轮询、高精度时间戳。
"""
import logging
import os
import asyncio
import tempfile
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

import dashscope
import requests
from dashscope.audio.asr import Transcription

from ..core.logging import logger
from ..core.config import settings
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
    """阿里云 Fun-ASR-Flash 语音识别服务"""
    
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

        if settings.DASHSCOPE_HTTP_BASE_URL:
            os.environ["DASHSCOPE_HTTP_BASE_URL"] = settings.DASHSCOPE_HTTP_BASE_URL
            dashscope.base_http_api_url = settings.DASHSCOPE_HTTP_BASE_URL
            logger.info(f"DashScope HTTP endpoint: {settings.DASHSCOPE_HTTP_BASE_URL}")
        
        # 检查API密钥
        if not self.api_key:
            logger.warning("阿里云 DashScope API密钥未设置,请设置环境变量: TRANSCRIPT_SERVICE_API_KEY, QWEN_API_KEY 或 DASHSCOPE_API_KEY")
            self.available = False
        else:
            self.available = True
            logger.info("阿里云 Fun-ASR-Flash 语音服务初始化成功")
        self.last_error: Optional[str] = None
        self.last_failure_stage: Optional[str] = None
    
    def is_available(self) -> bool:
        """检查语音服务是否可用"""
        return self.available and bool(self.api_key)

    def _redact_url_for_log(self, url: Optional[str]) -> str:
        """日志中隐藏签名URL的查询参数。"""
        if not url:
            return ""
        return url.split("?", 1)[0] + ("?[redacted]" if "?" in url else "")

    def _redact_signed_urls_in_text(self, value: Any) -> str:
        """Hide signed URL query strings before logging nested SDK payloads."""
        text = str(value)
        return re.sub(r"(https?://[^\s'\"<>]+?)\?[^\s'\"<>]+", r"\1?[redacted]", text)

    def _retry_delay_seconds(self, attempt: int) -> float:
        base = max(settings.PARAFORMER_TRANSCRIPTION_RETRY_BASE_SECONDS, 0)
        return min(base * (2 ** max(attempt - 1, 0)), 30)

    def _is_retryable_transcription_exception(self, exc: Exception) -> bool:
        if isinstance(
            exc,
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.SSLError,
            ),
        ):
            return True

        message = str(exc).lower()
        retryable_tokens = (
            "unexpected_eof",
            "eof occurred",
            "max retries exceeded",
            "connection reset",
            "temporarily unavailable",
            "timeout",
            "timed out",
        )
        return any(token in message for token in retryable_tokens)

    def _retryable_response_reason(self, response: Any) -> Optional[str]:
        if not response:
            return "empty response"

        status_code = getattr(response, "status_code", None)
        if status_code in {408, 429, 500, 502, 503, 504}:
            return f"HTTP {status_code}"
        return None

    async def _submit_transcription_task(
        self,
        audio_oss_url: str,
        enable_diarization: bool,
    ) -> Optional[Any]:
        max_attempts = max(settings.PARAFORMER_TRANSCRIPTION_SUBMIT_RETRIES, 1)

        for attempt in range(1, max_attempts + 1):
            try:
                response = Transcription.async_call(
                    model=settings.ASR_MODEL,
                    file_urls=[audio_oss_url],
                    diarization_enabled=enable_diarization,
                )
            except Exception as exc:
                if attempt < max_attempts and self._is_retryable_transcription_exception(exc):
                    delay = self._retry_delay_seconds(attempt)
                    logger.warning(
                        "转录任务提交失败，将重试 (%s/%s, %.1fs): %s",
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            retry_reason = self._retryable_response_reason(response)
            if retry_reason and attempt < max_attempts:
                delay = self._retry_delay_seconds(attempt)
                logger.warning(
                    "转录任务提交返回可重试响应，将重试 (%s/%s, %.1fs): %s",
                    attempt,
                    max_attempts,
                    delay,
                    retry_reason,
                )
                await asyncio.sleep(delay)
                continue

            return response

        return None

    async def _fetch_transcription_task(self, task_id: str) -> Optional[Any]:
        max_errors = max(settings.PARAFORMER_TRANSCRIPTION_FETCH_RETRIES, 0)
        errors = 0

        while True:
            try:
                response = Transcription.fetch(task=task_id)
            except Exception as exc:
                if errors < max_errors and self._is_retryable_transcription_exception(exc):
                    errors += 1
                    delay = self._retry_delay_seconds(errors)
                    logger.warning(
                        "查询转录任务状态失败，将继续重试 (%s/%s, %.1fs): %s",
                        errors,
                        max_errors,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            retry_reason = self._retryable_response_reason(response)
            if retry_reason and errors < max_errors:
                errors += 1
                delay = self._retry_delay_seconds(errors)
                logger.warning(
                    "查询转录任务状态返回可重试响应，将继续重试 (%s/%s, %.1fs): %s",
                    errors,
                    max_errors,
                    delay,
                    retry_reason,
                )
                await asyncio.sleep(delay)
                continue

            return response
    
    async def transcribe_audio_with_timestamps(
        self, 
        audio_oss_url: str, 
        language: str = "auto",
        enable_diarization: bool = True,
        enable_words: bool = True
    ) -> Optional[Any]:
        """
        使用阿里云 Fun-ASR-Flash API 转录音频并获取详细时间戳
        
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
            logger.info(f"开始转录音频文件: {self._redact_url_for_log(audio_oss_url)}")
            logger.info(f"配置 - 说话人分离: {enable_diarization}, 词级时间戳: {enable_words}")
            
            # 调用 Fun-ASR-Flash 异步转录 API
            # 参考: https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-python-sdk
            logger.info("发送转录请求到阿里云 Fun-ASR-Flash...")
            
            transcribe_response = await self._submit_transcription_task(
                audio_oss_url=audio_oss_url,
                enable_diarization=enable_diarization,
            )
            
            # 检查响应是否有效
            if not transcribe_response:
                self.last_error = "转录API调用失败: 返回空响应"
                self.last_failure_stage = "transcribing"
                logger.error(self.last_error)
                return None
            
            # 检查响应状态码
            if hasattr(transcribe_response, 'status_code') and transcribe_response.status_code != 200:
                error_msg = f"转录API调用失败: HTTP {transcribe_response.status_code}"
                if hasattr(transcribe_response, 'message'):
                    error_msg += f" - {transcribe_response.message}"
                self.last_error = error_msg
                self.last_failure_stage = "transcribing"
                logger.error(error_msg)
                return None
            
            # 检查output是否存在
            if not hasattr(transcribe_response, 'output') or transcribe_response.output is None:
                self.last_error = "转录API调用失败: 响应中没有output字段"
                self.last_failure_stage = "transcribing"
                logger.error(self.last_error)
                logger.error(f"完整响应: {self._redact_signed_urls_in_text(transcribe_response)}")
                return None
            
            # 获取任务ID
            if not hasattr(transcribe_response.output, 'task_id') or not transcribe_response.output.task_id:
                self.last_error = "转录API调用失败: 没有获取到task_id"
                self.last_failure_stage = "transcribing"
                logger.error(self.last_error)
                logger.error(f"完整output: {transcribe_response.output}")
                return None
                
            task_id = transcribe_response.output.task_id
            logger.info(f"转录任务已创建,任务ID: {task_id}")
            
            # 轮询任务状态
            max_wait_time = max(settings.PARAFORMER_MAX_WAIT_SECONDS, 30)
            poll_interval = max(settings.PARAFORMER_POLL_INTERVAL_SECONDS, 1)
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                # 等待一段时间后查询
                await asyncio.sleep(poll_interval)
                elapsed_time += poll_interval
                
                # 查询任务状态
                transcribe_response = await self._fetch_transcription_task(task_id)
                if not transcribe_response or not hasattr(transcribe_response, 'output') or transcribe_response.output is None:
                    self.last_error = "查询转录任务失败: 响应中没有output字段"
                    self.last_failure_stage = "transcribing"
                    logger.error(self.last_error)
                    return None

                task_status = transcribe_response.output.task_status
                
                logger.info(f"任务状态: {task_status} (已等待 {elapsed_time}s)")
                
                if task_status == "SUCCEEDED":
                    logger.info("转录任务成功完成")
                    return transcribe_response.output
                elif task_status == "FAILED":
                    error_msg = f"转录任务失败: {transcribe_response.output}"
                    self.last_error = error_msg
                    self.last_failure_stage = "transcribing"
                    logger.error(error_msg)
                    return None
            
            # 超时
            self.last_error = f"转录任务超时(超过 {max_wait_time}s)"
            self.last_failure_stage = "transcribing"
            logger.error(self.last_error)
            return None
                
        except Exception as e:
            self.last_error = str(e)
            self.last_failure_stage = "transcribing"
            logger.exception(f"转录过程中发生错误: {e}")
            return None
    
    def _parse_transcription_to_segments(
        self, 
        transcription_output: Any, 
        audio_oss_url: str
    ) -> Optional[TranscriptionResult]:
        """
        将阿里云 Fun-ASR-Flash 结果解析为段落级时间戳
        
        Fun-ASR-Flash 返回格式:
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
            logger.info("Fun-ASR-Flash 转录结果原始数据:")
            logger.info(f"transcription_output 类型: {type(transcription_output)}")
            logger.info(f"results 类型: {type(results)}")
            logger.info(f"results 数量: {len(results) if results else 0}")
            
            if results:
                logger.info(f"results[0] 类型: {type(results[0])}")
                preview = self._redact_signed_urls_in_text(results[0])[:500]
                logger.info(f"results[0] 内容预览: {preview}")
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
                    
                    # Fun-ASR-Flash 标准格式
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
        audio_oss_url: Optional[str] = None,
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
            self.last_error = None
            self.last_failure_stage = None
            audio_path = None
            audio_paths: List[str] = []
            chunk_dirs: List[str] = []

            if not audio_oss_url:
                duration = await self._probe_media_duration(video_path)
                chunk_seconds = max(settings.PARAFORMER_CHUNK_SECONDS, 1)
                if duration and duration > chunk_seconds:
                    chunks, chunk_dir = await self._extract_audio_chunks_with_ffmpeg(
                        video_path,
                        video_id,
                        chunk_seconds,
                    )
                    chunk_dirs.append(chunk_dir)
                    audio_paths.extend(chunk["path"] for chunk in chunks)
                    if chunks:
                        return await self._transcribe_audio_chunks(
                            chunks,
                            video_id,
                            enable_diarization=enable_diarization,
                        )

                # 使用ffmpeg提取音频
                audio_path = await self._extract_audio_with_ffmpeg(video_path, video_id)
                if audio_path:
                    audio_paths.append(audio_path)

                if not audio_path:
                    self.last_error = "音频提取失败"
                    self.last_failure_stage = "extracting_audio"
                    logger.error(self.last_error)
                    return None

                # Paraformer 需要公共URL；Slim 本地模式下没有 OSS 时降级为空转录。
                if not settings.ENABLE_OSS_UPLOADS:
                    self.last_error = "OSS上传已禁用，跳过Paraformer转录"
                    self.last_failure_stage = "uploading_audio"
                    logger.warning(self.last_error)
                    return None

                try:
                    from .oss_service import oss_service
                    if not oss_service.is_available():
                        self.last_error = "OSS服务不可用,Paraformer 需要音频的公共URL"
                        self.last_failure_stage = "uploading_audio"
                        logger.error(self.last_error)
                        return None

                    audio_oss_url_temp = await oss_service.upload_audio(audio_path, video_id)
                    if not audio_oss_url_temp:
                        self.last_error = "OSS上传返回空URL"
                        self.last_failure_stage = "uploading_audio"
                        logger.error(self.last_error)
                        return None
                    audio_oss_url = audio_oss_url_temp
                    logger.info(f"音频已上传到OSS: {self._redact_url_for_log(audio_oss_url)}")

                except Exception as e:
                    self.last_error = str(e)
                    self.last_failure_stage = "uploading_audio"
                    logger.error(f"OSS上传失败,无法进行转录: {e}")
                    return None

            # 转录音频(使用OSS URL)
            transcription_output = await self.transcribe_audio_with_timestamps(
                audio_oss_url,
                enable_diarization=enable_diarization
            )
            
            if not transcription_output:
                if not self.last_error:
                    self.last_error = "音频转录失败"
                self.last_failure_stage = self.last_failure_stage or "transcribing"
                logger.error(self.last_error)
                return None
            
            # 解析转录结果
            result = self._parse_transcription_to_segments(transcription_output, audio_oss_url)
            if result:
                self._annotate_result(result, provider="paraformer")
            
            return result
            
        except Exception as e:
            self.last_error = str(e)
            self.last_failure_stage = self.last_failure_stage or "extracting_audio"
            logger.exception(f"音频提取和转录失败: {e}")
            return None
        finally:
            for path in audio_paths:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        logger.debug(f"已清理本地音频文件: {path}")
                    except Exception as e:
                        logger.warning(f"清理本地音频文件失败: {e}")
            for directory in chunk_dirs:
                if directory and os.path.isdir(directory):
                    try:
                        os.rmdir(directory)
                    except OSError:
                        pass

    def _audio_extension(self) -> str:
        return "wav" if settings.PARAFORMER_AUDIO_FORMAT == "wav" else "flac"

    def _audio_codec(self) -> str:
        return "pcm_s16le" if self._audio_extension() == "wav" else "flac"

    async def _probe_media_duration(self, video_path: str) -> Optional[float]:
        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await process.communicate()
            if process.returncode != 0:
                return None
            return float(stdout.decode().strip() or 0)
        except Exception as e:
            logger.warning(f"探测媒体时长失败，回退到单文件音频提取: {e}")
            return None

    async def _extract_audio_chunks_with_ffmpeg(
        self,
        video_path: str,
        video_id: str,
        chunk_seconds: int,
    ) -> Tuple[List[Dict[str, Any]], str]:
        extension = self._audio_extension()
        chunk_dir = tempfile.mkdtemp(prefix=f"{video_id}_audio_chunks_")
        output_pattern = os.path.join(chunk_dir, f"{video_id}_chunk_%03d.{extension}")

        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            self._audio_codec(),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            output_pattern,
            "-y",
        ]

        logger.info(f"使用ffmpeg分段提取音频: {video_path} -> {output_pattern}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"ffmpeg分段提取音频失败: {stderr.decode()}")
            return [], chunk_dir

        chunk_paths = sorted(str(path) for path in Path(chunk_dir).glob(f"*.{extension}"))
        chunks = [
            {
                "path": path,
                "offset": index * chunk_seconds,
                "chunk_id": f"chunk_{index:03d}",
            }
            for index, path in enumerate(chunk_paths)
        ]
        logger.info(f"音频分段提取成功: {len(chunks)} chunks")
        return chunks, chunk_dir

    async def _transcribe_audio_chunks(
        self,
        chunks: List[Dict[str, Any]],
        video_id: str,
        enable_diarization: bool,
    ) -> Optional[TranscriptionResult]:
        if not settings.ENABLE_OSS_UPLOADS:
            self.last_error = "OSS上传已禁用，跳过Paraformer分段转录"
            self.last_failure_stage = "uploading_audio"
            logger.warning(self.last_error)
            return None

        from .oss_service import oss_service

        if not oss_service.is_available():
            self.last_error = "OSS服务不可用,Paraformer 分段转录需要音频公共URL"
            self.last_failure_stage = "uploading_audio"
            logger.error(self.last_error)
            return None

        semaphore = asyncio.Semaphore(max(settings.PARAFORMER_MAX_PARALLEL_CHUNKS, 1))

        async def transcribe_chunk(chunk: Dict[str, Any]) -> Optional[TranscriptionResult]:
            async with semaphore:
                audio_url = await oss_service.upload_audio(chunk["path"], video_id)
                if not audio_url:
                    self.last_error = f"音频分段上传失败: {chunk['chunk_id']}"
                    self.last_failure_stage = "uploading_audio"
                    logger.error(self.last_error)
                    return None
                output = await self.transcribe_audio_with_timestamps(
                    audio_url,
                    enable_diarization=enable_diarization,
                )
                if not output:
                    if not self.last_error:
                        self.last_error = f"音频分段转录失败: {chunk['chunk_id']}"
                    self.last_failure_stage = self.last_failure_stage or "transcribing"
                    logger.error(f"音频分段转录失败: {chunk['chunk_id']}")
                    return None
                result = self._parse_transcription_to_segments(output, audio_url)
                if result:
                    self._annotate_result(
                        result,
                        provider="paraformer",
                        chunk_id=chunk["chunk_id"],
                        offset=float(chunk["offset"]),
                    )
                return result

        results = await asyncio.gather(*(transcribe_chunk(chunk) for chunk in chunks))
        valid_results = [result for result in results if result]
        if not valid_results:
            return None
        if len(valid_results) != len(chunks):
            logger.warning(f"部分音频分段转录失败: {len(valid_results)}/{len(chunks)}")
        return self._merge_chunk_results(valid_results)

    def _annotate_result(
        self,
        result: TranscriptionResult,
        provider: str,
        chunk_id: Optional[str] = None,
        offset: float = 0.0,
    ) -> None:
        for segment in result.segments:
            segment.provider = provider
            segment.chunk_id = chunk_id
            if offset:
                segment.start_time += offset
                segment.end_time += offset

    def _merge_chunk_results(self, results: List[TranscriptionResult]) -> TranscriptionResult:
        segments: List[TranscriptSegment] = []
        audio_urls: List[str] = []
        speaker_count = 0
        for result in results:
            segments.extend(result.segments)
            audio_urls.append(result.audio_oss_url)
            speaker_count = max(speaker_count, result.speaker_count)

        segments.sort(key=lambda segment: (segment.start_time, segment.end_time))
        confidence = (
            sum(segment.confidence for segment in segments) / len(segments)
            if segments else 0.0
        )
        return TranscriptionResult(
            segments=segments,
            language=results[0].language if results else "unknown",
            confidence=confidence,
            audio_oss_url=",".join(audio_urls),
            full_text=" ".join(segment.text for segment in segments),
            speaker_count=speaker_count,
        )
    
    async def _extract_audio_with_ffmpeg(self, video_path: str, video_id: str) -> Optional[str]:
        """
        使用ffmpeg提取音频,针对 Paraformer 优化
        
        Paraformer 建议:
        - 单声道 (说话人分离仅支持单声道)
        - 16kHz 采样率
        - Slim 默认使用 FLAC 压缩，避免长视频生成超大 WAV
        """
        try:
            # 生成临时音频文件路径
            temp_dir = tempfile.gettempdir()
            extension = self._audio_extension()
            audio_path = os.path.join(temp_dir, f"{video_id}_audio_paraformer.{extension}")
            
            # ffmpeg命令 - 针对 Paraformer 优化
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn',                      # 不处理视频
                '-acodec', self._audio_codec(),
                '-ar', '16000',             # 16kHz采样率
                '-ac', '1',                 # 单声道 (说话人分离要求)
                '-f', extension,
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
                self.last_error = f"ffmpeg提取音频失败: {stderr.decode()[:500]}"
                self.last_failure_stage = "extracting_audio"
                logger.error(f"ffmpeg提取音频失败: {stderr.decode()}")
                return None
                
        except Exception as e:
            self.last_error = str(e)
            self.last_failure_stage = "extracting_audio"
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
            if result:
                self._annotate_result(result, provider="paraformer")
            
            return result
            
        except Exception as e:
            logger.exception(f"音频文件转录失败: {e}")
            return None


# 创建单例实例
paraformer_service = ParaformerSpeechService()
