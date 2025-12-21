"""
YouTube字幕获取服务
使用 yt-dlp 获取 YouTube 视频字幕，支持代理和 Cookies
保护服务器IP，避免被YouTube封禁
"""
import os
import re
import json
import asyncio
import tempfile
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from ..core.logging import logger
from ..core.config import settings
from ..models.analysis import TranscriptSegment, TranscriptMetadata


@dataclass
class YouTubeVideoInfo:
    """YouTube视频基本信息"""
    video_id: str
    title: str
    duration: float
    channel_name: str
    channel_id: str
    thumbnail_url: str
    published_at: Optional[datetime]
    has_transcript: bool
    available_languages: List[str]


@dataclass
class TranscriptResult:
    """字幕获取结果"""
    video_id: str
    segments: List[TranscriptSegment]
    language: str
    is_auto_generated: bool
    full_text: str


class YouTubeTranscriptService:
    """
    YouTube字幕获取服务
    
    使用 yt-dlp 获取字幕，支持：
    - 代理配置 (YOUTUBE_PROXY)
    - Cookies 文件 (youtube_cookies.txt)
    - 多语言优先级
    
    核心原则：只获取字幕，不下载视频文件
    """
    
    def __init__(self):
        """初始化字幕服务"""
        self.proxy = getattr(settings, 'YOUTUBE_PROXY', None) or os.getenv("YOUTUBE_PROXY")
        
        # Cookies 文件路径
        backend_dir = Path(__file__).parent.parent.parent
        self.cookies_file = backend_dir / "youtube_cookies.txt"
        
        if not self.cookies_file.exists():
            self.cookies_file = None
            logger.warning("YouTube Cookies 文件不存在，部分功能可能受限")
        
        if yt_dlp is None:
            logger.error("yt-dlp 未安装，字幕服务将不可用")
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """
        从YouTube URL中提取视频ID
        
        支持的格式:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        """
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # 如果URL本身就是11位的视频ID
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
            return url
        
        return None
    
    def _get_ydl_opts(self, temp_dir: str, subtitle_langs: List[str] = None) -> dict:
        """获取 yt-dlp 配置选项"""
        if subtitle_langs is None:
            subtitle_langs = ['zh-Hans', 'zh-Hant', 'zh', 'en', 'ja', 'ko']
        
        opts = {
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            
            # 字幕配置
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': subtitle_langs,
            'subtitlesformat': 'json3/srv3/vtt/srt/best',
            
            # 只获取字幕，不下载视频
            'skip_download': True,
            
            # 输出目录
            'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
            
            # HTTP 头配置
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            },
        }
        
        # 添加代理
        if self.proxy:
            opts['proxy'] = self.proxy
        
        # 添加 Cookies
        if self.cookies_file and self.cookies_file.exists():
            opts['cookiefile'] = str(self.cookies_file)
        
        return opts
    
    def _parse_json3_subtitle(self, file_path: str) -> List[TranscriptSegment]:
        """解析 json3 格式字幕文件"""
        segments = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            events = data.get('events', [])
            
            for event in events:
                # 跳过没有文本的事件
                segs = event.get('segs', [])
                if not segs:
                    continue
                
                # 提取文本
                text_parts = []
                for seg in segs:
                    if 'utf8' in seg:
                        text_parts.append(seg['utf8'])
                
                text = ''.join(text_parts).strip()
                if not text:
                    continue
                
                # 时间戳（毫秒转秒）
                start_ms = event.get('tStartMs', 0)
                duration_ms = event.get('dDurationMs', 0)
                
                start_time = start_ms / 1000.0
                end_time = (start_ms + duration_ms) / 1000.0
                
                segment = TranscriptSegment(
                    text=text,
                    start_time=start_time,
                    end_time=end_time,
                    confidence=0.9  # json3 通常是自动生成的
                )
                segments.append(segment)
                
        except Exception as e:
            logger.error(f"解析 json3 字幕失败: {e}")
        
        return segments
    
    def _parse_vtt_subtitle(self, file_path: str) -> List[TranscriptSegment]:
        """解析 VTT/SRT 格式字幕文件"""
        segments = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单的 VTT/SRT 解析
            lines = content.split('\n')
            current_start = 0.0
            current_end = 0.0
            current_text = []
            
            for line in lines:
                line = line.strip()
                
                # 跳过 WEBVTT 头和空行
                if not line or line.startswith('WEBVTT') or line.startswith('NOTE'):
                    continue
                
                # 时间戳行
                if '-->' in line:
                    # 保存之前的段落
                    if current_text:
                        text = ' '.join(current_text).strip()
                        if text:
                            segments.append(TranscriptSegment(
                                text=text,
                                start_time=current_start,
                                end_time=current_end,
                                confidence=0.95
                            ))
                        current_text = []
                    
                    # 解析时间戳
                    parts = line.split('-->')
                    if len(parts) == 2:
                        current_start = self._parse_timestamp(parts[0].strip())
                        current_end = self._parse_timestamp(parts[1].strip().split()[0])
                    continue
                
                # 跳过数字行（SRT格式）
                if line.isdigit():
                    continue
                
                # 文本行
                current_text.append(line)
            
            # 保存最后一个段落
            if current_text:
                text = ' '.join(current_text).strip()
                if text:
                    segments.append(TranscriptSegment(
                        text=text,
                        start_time=current_start,
                        end_time=current_end,
                        confidence=0.95
                    ))
                    
        except Exception as e:
            logger.error(f"解析 VTT 字幕失败: {e}")
        
        return segments
    
    def _parse_timestamp(self, timestamp: str) -> float:
        """解析时间戳字符串为秒数"""
        try:
            # 移除可能的位置信息
            timestamp = timestamp.split()[0]
            
            # 格式: HH:MM:SS.mmm 或 MM:SS.mmm
            parts = timestamp.replace(',', '.').split(':')
            
            if len(parts) == 3:
                hours, minutes, seconds = parts
                return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
            elif len(parts) == 2:
                minutes, seconds = parts
                return float(minutes) * 60 + float(seconds)
            else:
                return float(parts[0])
        except:
            return 0.0
    
    async def check_transcript_availability(self, youtube_url: str) -> Dict[str, Any]:
        """
        检查YouTube视频是否有可用字幕
        
        Args:
            youtube_url: YouTube视频URL
            
        Returns:
            {
                "video_id": "xxx",
                "has_transcript": True/False,
                "available_languages": ["en", "zh-Hans", ...],
                "has_manual_transcript": True/False,
                "has_auto_generated": True/False,
                "error": None or "错误信息"
            }
        """
        if yt_dlp is None:
            return {
                "video_id": None,
                "has_transcript": False,
                "available_languages": [],
                "has_manual_transcript": False,
                "has_auto_generated": False,
                "error": "yt-dlp 未安装"
            }
        
        video_id = self._extract_video_id(youtube_url)
        
        if not video_id:
            return {
                "video_id": None,
                "has_transcript": False,
                "available_languages": [],
                "has_manual_transcript": False,
                "has_auto_generated": False,
                "error": "无效的YouTube URL"
            }
        
        try:
            # 使用 yt-dlp 获取视频信息（不下载）
            with tempfile.TemporaryDirectory() as temp_dir:
                opts = self._get_ydl_opts(temp_dir)
                opts['skip_download'] = True
                opts['writesubtitles'] = False
                opts['writeautomaticsub'] = False
                
                def extract():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(youtube_url, download=False)
                
                info = await asyncio.to_thread(extract)
                
                if not info:
                    return {
                        "video_id": video_id,
                        "has_transcript": False,
                        "available_languages": [],
                        "has_manual_transcript": False,
                        "has_auto_generated": False,
                        "error": "无法获取视频信息"
                    }
                
                subtitles = info.get('subtitles', {})
                automatic_captions = info.get('automatic_captions', {})
                
                available_languages = list(set(list(subtitles.keys()) + list(automatic_captions.keys())))
                
                return {
                    "video_id": video_id,
                    "has_transcript": bool(subtitles or automatic_captions),
                    "available_languages": available_languages,
                    "has_manual_transcript": bool(subtitles),
                    "has_auto_generated": bool(automatic_captions),
                    "error": None,
                    "title": info.get('title'),
                    "duration": info.get('duration', 0),
                    "channel": info.get('channel', info.get('uploader'))
                }
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"检查字幕可用性失败: {error_msg[:200]}")
            
            # 分析错误原因
            if "Sign in to confirm" in error_msg or "confirm your age" in error_msg:
                error = "需要登录验证，请更新 Cookies"
            elif "Video unavailable" in error_msg:
                error = "视频不可用或已被删除"
            elif "Private video" in error_msg:
                error = "这是私密视频"
            else:
                error = f"获取视频信息失败: {error_msg[:100]}"
            
            return {
                "video_id": video_id,
                "has_transcript": False,
                "available_languages": [],
                "has_manual_transcript": False,
                "has_auto_generated": False,
                "error": error
            }
        except Exception as e:
            logger.exception(f"检查字幕可用性异常: {e}")
            return {
                "video_id": video_id,
                "has_transcript": False,
                "available_languages": [],
                "has_manual_transcript": False,
                "has_auto_generated": False,
                "error": f"检查字幕失败: {str(e)}"
            }
    
    async def get_transcript(
        self, 
        youtube_url: str,
        preferred_languages: List[str] = None
    ) -> Optional[TranscriptResult]:
        """
        获取YouTube视频字幕
        
        Args:
            youtube_url: YouTube视频URL
            preferred_languages: 首选语言列表，按优先级排序
                                默认 ["zh-Hans", "zh-Hant", "zh", "en"]
            
        Returns:
            TranscriptResult 或 None
        """
        if yt_dlp is None:
            logger.error("yt-dlp 未安装")
            return None
        
        if preferred_languages is None:
            preferred_languages = ["zh-Hans", "zh-Hant", "zh", "en", "ja", "ko"]
        
        video_id = self._extract_video_id(youtube_url)
        
        if not video_id:
            logger.error(f"无效的YouTube URL: {youtube_url}")
            return None
        
        try:
            # 获取字幕
            
            with tempfile.TemporaryDirectory() as temp_dir:
                opts = self._get_ydl_opts(temp_dir, preferred_languages)
                
                def download():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(youtube_url, download=True)
                
                info = await asyncio.to_thread(download)
                
                if not info:
                    logger.warning(f"无法获取视频信息: {youtube_url}")
                    return None
                
                # 查找下载的字幕文件
                subtitle_files = []
                for f in os.listdir(temp_dir):
                    if f.endswith(('.json3', '.vtt', '.srt', '.srv3', '.ttml')):
                        subtitle_files.append(os.path.join(temp_dir, f))
                
                if not subtitle_files:
                    logger.warning(f"没有下载到字幕文件: {video_id}")
                    return None
                
                # 按语言优先级选择字幕文件
                selected_file = None
                selected_language = None
                is_auto_generated = True
                
                for lang in preferred_languages:
                    for sf in subtitle_files:
                        if f".{lang}." in sf:
                            selected_file = sf
                            selected_language = lang
                            break
                    if selected_file:
                        break
                
                # 如果没有找到首选语言，使用第一个可用的
                if not selected_file and subtitle_files:
                    selected_file = subtitle_files[0]
                    # 从文件名提取语言
                    filename = os.path.basename(selected_file)
                    parts = filename.split('.')
                    if len(parts) >= 3:
                        selected_language = parts[-2]
                    else:
                        selected_language = "unknown"
                
                if not selected_file:
                    return None
                
                # 使用字幕文件
                
                # 解析字幕文件
                if selected_file.endswith('.json3'):
                    segments = self._parse_json3_subtitle(selected_file)
                else:
                    segments = self._parse_vtt_subtitle(selected_file)
                
                if not segments:
                    logger.warning(f"字幕文件解析失败或为空: {selected_file}")
                    return None
                
                # 构建完整文本
                full_text = ' '.join(seg.text for seg in segments)
                
                # 成功获取字幕
                
                return TranscriptResult(
                    video_id=video_id,
                    segments=segments,
                    language=selected_language,
                    is_auto_generated=is_auto_generated,
                    full_text=full_text
                )
                
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"下载字幕失败: {e}")
            return None
        except Exception as e:
            logger.exception(f"获取字幕异常: {e}")
            return None
    
    async def get_transcript_as_metadata(
        self,
        youtube_url: str,
        preferred_languages: List[str] = None
    ) -> Optional[TranscriptMetadata]:
        """
        获取字幕并转换为TranscriptMetadata格式
        
        Args:
            youtube_url: YouTube视频URL
            preferred_languages: 首选语言列表
            
        Returns:
            TranscriptMetadata 或 None
        """
        result = await self.get_transcript(youtube_url, preferred_languages)
        
        if result is None:
            return None
        
        # 计算整体置信度
        if result.segments:
            overall_confidence = sum(s.confidence for s in result.segments) / len(result.segments)
        else:
            overall_confidence = 0.0
        
        return TranscriptMetadata(
            oss_audio_url="",  # 字幕模式不需要音频URL
            language=result.language,
            overall_confidence=overall_confidence,
            segments=result.segments
        )
    
    async def get_video_info(self, youtube_url: str) -> Optional[Dict[str, Any]]:
        """
        获取视频基本信息（不下载）
        
        Args:
            youtube_url: YouTube视频URL
            
        Returns:
            视频信息字典
        """
        availability = await self.check_transcript_availability(youtube_url)
        
        if availability.get("error"):
            return None
        
        return {
            "video_id": availability.get("video_id"),
            "title": availability.get("title"),
            "duration": availability.get("duration"),
            "channel": availability.get("channel"),
            "has_transcript": availability.get("has_transcript"),
            "available_languages": availability.get("available_languages")
        }
    
    def get_client_download_instructions(self, youtube_url: str) -> Dict[str, Any]:
        """
        获取客户端下载指令
        当视频没有字幕时，引导用户在本地下载
        
        Args:
            youtube_url: YouTube视频URL
            
        Returns:
            下载指令和建议
        """
        video_id = self._extract_video_id(youtube_url)
        
        return {
            "video_id": video_id,
            "youtube_url": youtube_url,
            "instructions": {
                "title": "该视频没有可用字幕，请使用以下方式下载视频",
                "methods": [
                    {
                        "name": "yt-dlp (推荐)",
                        "description": "开源命令行工具，功能强大",
                        "install": "pip install yt-dlp",
                        "command": f"yt-dlp -f 'bestaudio[ext=m4a]/bestaudio' -o 'audio.%(ext)s' '{youtube_url}'",
                        "note": "仅下载音频，节省带宽"
                    },
                    {
                        "name": "浏览器扩展",
                        "description": "方便快捷的浏览器下载扩展",
                        "suggestions": [
                            "Video DownloadHelper (Firefox/Chrome)",
                            "SaveFrom.net Helper",
                            "4K Video Downloader"
                        ]
                    },
                    {
                        "name": "在线工具",
                        "description": "无需安装的在线下载服务",
                        "suggestions": [
                            "y2mate.com",
                            "savefrom.net",
                            "9xbuddy.com"
                        ],
                        "warning": "请注意这些网站可能包含广告"
                    }
                ],
                "tips": [
                    "建议仅下载音频文件以节省带宽和时间",
                    "下载后请上传音频文件（支持mp3, m4a, wav, flac格式）",
                    "我们将使用AI进行语音转录和分析"
                ]
            }
        }
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return yt_dlp is not None


# 创建单例实例
youtube_transcript_service = YouTubeTranscriptService()
