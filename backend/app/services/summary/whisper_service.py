import os
import logging
import tempfile
from typing import Optional, Dict, Any, Union, List, Tuple
from pathlib import Path
import json
import math
import shutil
from dotenv import load_dotenv

# 确保环境变量在服务实例化时已加载
load_dotenv(verbose=True)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    logging.info("成功导入OpenAI模块")
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("未找到OpenAI模块，将无法使用Whisper API")

try:
    from pyannote.audio import Pipeline
    PYANNOTE_AVAILABLE = True
    logging.info("成功导入pyannote.audio模块")
except ImportError:
    PYANNOTE_AVAILABLE = False
    logging.warning("未找到pyannote.audio模块，说话人分离功能将不可用")

from app.core.config import settings

# 配置日志
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# 打印环境变量值以便调试
logger.info(f"whisper_service模块: OPENAI_API_KEY 存在: {'是' if os.getenv('OPENAI_API_KEY') else '否'}")
logger.info(f"whisper_service模块: HF_TOKEN 存在: {'是' if os.getenv('HF_TOKEN') else '否'}")
logger.info(f"whisper_service模块: 当前工作目录: {os.getcwd()}")

class WhisperService:
    """Whisper API服务，用于语音转文本"""
    
    def __init__(self):
        """初始化Whisper API服务"""
        # 从环境变量获取API密钥
        self.api_key = os.getenv("OPENAI_API_KEY")
        
        # 添加详细的调试日志
        logger.info("开始初始化Whisper API服务")
        logger.info(f"OpenAI模块是否可用: {OPENAI_AVAILABLE}")
        logger.info(f"OPENAI_API_KEY是否存在: {self.api_key is not None}")
        
        if not self.api_key:
            logger.error("OPENAI_API_KEY环境变量未设置")
            self.available = False
            self.client = None
        elif not OPENAI_AVAILABLE:
            logger.error("OpenAI模块导入失败，请检查是否已安装: pip install openai")
            self.available = False
            self.client = None
        else:
            try:
                self.available = True
                # 初始化OpenAI客户端
                self.client = OpenAI(api_key=self.api_key)
                # 验证API密钥是否有效
                try:
                    # 尝试一个简单的API调用来验证密钥
                    self.client.models.list()
                    logger.info("OpenAI API密钥验证成功")
                except Exception as e:
                    logger.error(f"OpenAI API密钥验证失败: {str(e)}")
                    self.available = False
                    self.client = None
                
                # 最大文件大小限制 (字节)
                self.max_file_size = 25 * 1024 * 1024  # 25MB
                
                logger.info("Whisper API服务初始化完成")
            except Exception as e:
                logger.error(f"初始化OpenAI客户端时出错: {str(e)}")
                self.available = False
                self.client = None
        
        # 初始化说话人分离模型（如果可用）
        self.diarization_pipeline = None
        self.diarization_available = False
        
        if PYANNOTE_AVAILABLE:
            try:
                # 检查环境变量HF_TOKEN
                hf_token = os.getenv("HF_TOKEN")
                if hf_token:
                    # 初始化说话人分离模型
                    self.diarization_pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.1",
                        use_auth_token=hf_token
                    )
                    self.diarization_available = True
                    logger.info("说话人分离功能可用")
                else:
                    logger.warning("未设置HF_TOKEN环境变量，说话人分离功能将不可用")
            except Exception as e:
                logger.error(f"加载说话人分离模型失败: {str(e)}")
    
    def is_available(self) -> bool:
        """检查Whisper API服务是否可用"""
        return self.available and OPENAI_AVAILABLE and self.api_key is not None
    
    def is_diarization_available(self) -> bool:
        """检查说话人分离功能是否可用"""
        return self.diarization_available and self.diarization_pipeline is not None
    
    def _get_file_size(self, file_path: str) -> int:
        """获取文件大小 (字节)"""
        return os.path.getsize(file_path)
    
    def _format_timestamp(self, seconds: float) -> str:
        """将秒转换为HH:MM:SS格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    
    def _split_audio_file(self, file_path: str, max_size_mb: int = 25):
        """
        将大型音频文件分割成小于25MB的片段
        - 计算每段时长
        - 分割并保存临时文件
        - 返回分割文件列表
        """
        logger.info(f"分割音频文件: {file_path}, 最大大小: {max_size_mb}MB")
        
        # 导入必要的库
        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error("未找到pydub模块，无法分割音频文件")
            return []
        
        # 载入音频文件
        try:
            audio = AudioSegment.from_file(file_path)
        except Exception as e:
            logger.error(f"载入音频文件失败: {str(e)}")
            return []
        
        # 计算分割数量和每段时长
        total_seconds = len(audio) / 1000  # 毫秒转秒
        file_size_mb = self._get_file_size(file_path) / (1024 * 1024)
        
        # 估计每秒占用的MB数
        mb_per_second = file_size_mb / total_seconds if total_seconds > 0 else 0
        
        # 计算每段的最大秒数
        seconds_per_chunk = int(max_size_mb / mb_per_second) if mb_per_second > 0 else 0
        
        # 安全检查
        if seconds_per_chunk <= 0:
            logger.error("无法计算合适的分割大小")
            return []
        
        # 计算需要分割的块数
        num_chunks = math.ceil(total_seconds / seconds_per_chunk)
        logger.info(f"将音频分割为{num_chunks}个片段，每段最长{seconds_per_chunk}秒")
        
        # 创建临时文件夹
        temp_dir = tempfile.mkdtemp()
        
        # 分割文件
        chunk_files = []
        for i in range(num_chunks):
            start_ms = i * seconds_per_chunk * 1000
            end_ms = min((i + 1) * seconds_per_chunk * 1000, len(audio))
            
            # 计算起始时间(秒)
            start_seconds = start_ms / 1000
            
            chunk = audio[start_ms:end_ms]
            
            # 保存分割文件
            chunk_file = os.path.join(temp_dir, f"chunk_{i}.mp3")
            chunk.export(chunk_file, format="mp3")
            
            # 保存文件路径和起始时间
            chunk_files.append((chunk_file, start_seconds))
            logger.info(f"已创建分割文件: {chunk_file}, 大小: {self._get_file_size(chunk_file) / (1024 * 1024):.2f}MB, 起始时间: {self._format_timestamp(start_seconds)}")
        
        return chunk_files
    
    def transcribe_audio(self, audio_file: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        使用 Whisper API 转录音频
        """
        try:
            # 检查文件大小
            file_size = os.path.getsize(audio_file) / (1024 * 1024)  # 转换为MB
            logger.info(f"音频文件大小: {file_size:.2f}MB")
            
            if file_size > 25:
                logger.warning("音频文件超过25MB的限制，需要分段处理")
                return {"error": "音频文件过大，暂不支持处理"}
            
            logger.info("音频文件小于25MB的限制，直接转录")
            
            # 打开音频文件
            with open(audio_file, "rb") as audio:
                # 调用Whisper API
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language=language if language else None,
                    response_format="verbose_json"
                )
                
                return {
                    "text": response.text,
                    "segments": response.segments if hasattr(response, 'segments') else []
                }
                
        except Exception as e:
            logger.error(f"转录音频时出错: {str(e)}")
            return {"error": str(e)}
    
    def perform_speaker_diarization(self, audio_path: str):
        """
        说话人分离功能：
        1. 使用pyannote模型识别不同说话人
        2. 记录每个说话人的片段
        3. 统计说话时长和次数
        4. 重命名说话人（如"说话人1"、"说话人2"等）
        """
        logger.info(f"开始对音频进行说话人分离: {audio_path}")
        
        # 检查是否可用说话人分离功能
        if not self.is_diarization_available():
            error_msg = "说话人分离功能不可用，请确保已安装pyannote.audio并设置了HF_TOKEN环境变量"
            logger.error(error_msg)
            return {"error": error_msg}
        
        try:
            # 去除文件前缀 (如果有)
            if audio_path.startswith("file://"):
                audio_path = audio_path[7:]
            
            # 检查文件是否存在
            if not os.path.exists(audio_path):
                error_msg = f"音频文件不存在: {audio_path}"
                logger.error(error_msg)
                return {"error": error_msg}
            
            # 执行说话人分离
            diarization = self.diarization_pipeline(audio_path)
            
            # 解析结果
            result = {}
            result['speakers'] = {}
            
            # 包含所有的说话片段
            segments = []
            
            # 处理每个说话人片段
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = {
                    'speaker': speaker,
                    'start': turn.start,
                    'end': turn.end
                }
                segments.append(segment)
                
                # 记录说话人总时长
                if speaker not in result['speakers']:
                    result['speakers'][speaker] = {
                        'total_time': 0,
                        'segments_count': 0
                    }
                
                result['speakers'][speaker]['total_time'] += (turn.end - turn.start)
                result['speakers'][speaker]['segments_count'] += 1
            
            # 按时间顺序排序片段
            segments.sort(key=lambda x: x['start'])
            result['segments'] = segments
            
            # 统计信息
            total_speakers = len(result['speakers'])
            total_segments = len(segments)
            
            logger.info(f"说话人分离完成: 检测到{total_speakers}个说话人，共{total_segments}个片段")
            
            result['summary'] = {
                'total_speakers': total_speakers,
                'total_segments': total_segments
            }
            
            # 重命名说话人为更有用的名称
            speaker_mapping = {}
            for i, speaker in enumerate(result['speakers'].keys()):
                speaker_mapping[speaker] = f"说话人{i+1}"
            
            # 应用说话人重命名
            for segment in result['segments']:
                segment['speaker_display'] = speaker_mapping[segment['speaker']]
            
            result['speaker_mapping'] = speaker_mapping
            
            return result
            
        except Exception as e:
            error_msg = f"执行说话人分离时出错: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
    
    def transcribe_audio_with_speakers(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        将音频文件转换为带说话人标识的文本
        
        Args:
            audio_path: 音频文件路径
            language: 语言代码 (可选)
            
        Returns:
            Dict: 包含转录文本、说话人信息和元数据的字典
        """
        logger.info(f"开始转录带说话人标识的音频: {audio_path}")
        
        # 首先执行说话人分离
        diarization_result = self.perform_speaker_diarization(audio_path)
        
        # 如果说话人分离失败，回退到普通转录
        if "error" in diarization_result:
            logger.warning(f"说话人分离失败: {diarization_result['error']}")
            return self.transcribe_audio(audio_path)
        
        try:
            # 获取说话人片段
            segments = diarization_result.get("segments", [])
            
            # 对每个说话人片段进行转录
            for segment in segments:
                start_time = segment["start"]
                end_time = segment["end"]
                speaker = segment["speaker_display"]
                
                # 提取这个时间段的音频
                segment_audio = self._extract_audio_segment(audio_path, start_time, end_time)
                
                # 转录这个片段
                with open(segment_audio, "rb") as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language
                    )
                
                # 添加转录文本到片段
                segment["text"] = response.text
                
                # 删除临时文件
                os.remove(segment_audio)
            
            # 生成带说话人标识的完整文本
            full_text = ""
            for segment in segments:
                timestamp = self._format_timestamp(segment["start"])
                speaker = segment["speaker_display"]
                text = segment["text"]
                full_text += f"[{timestamp}] {speaker}：{text}\n"
            
            return {
                "text": full_text,
                "text_with_speakers": full_text,
                "segments": segments,
                "speakers": diarization_result["speakers"],
                "speaker_mapping": diarization_result["speaker_mapping"]
            }
            
        except Exception as e:
            error_msg = f"转录带说话人标识的音频时出错: {str(e)}"
            logger.error(error_msg)
            # 出错时回退到普通转录
            return self.transcribe_audio(audio_path)
    
    def _extract_audio_segment(self, audio_path: str, start_time: float, end_time: float) -> str:
        """提取音频片段的辅助方法"""
        import ffmpeg
        
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            # 使用ffmpeg提取音频片段
            (
                ffmpeg
                .input(audio_path)
                .output(temp_path, ss=start_time, t=end_time-start_time)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return temp_path
        except Exception as e:
            logger.error(f"提取音频片段失败: {str(e)}")
            raise

# 创建Whisper服务实例
whisper_service = WhisperService() 