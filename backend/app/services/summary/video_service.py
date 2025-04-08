import os
import shutil
import logging
import uuid
from typing import Dict, Any, Optional, List
from pathlib import Path
import yt_dlp
from datetime import datetime

from app.core.config import settings
from app.models.summary import SummaryCreate, SummaryInDB
from app.services.storage.json_storage import JSONStorage

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建摘要存储服务
summary_storage = JSONStorage[SummaryInDB](settings.SUMMARIES_DATA_FILE, SummaryInDB)

# 从YouTube URL中提取视频ID
def extract_video_id(url: str) -> str:
    """从YouTube URL中提取视频ID"""
    if "youtu.be" in url:
        # 处理短链接格式 (例如: https://youtu.be/VIDEO_ID)
        video_id = url.split("/")[-1].split("?")[0]
    elif "youtube.com/watch" in url:
        # 处理标准格式 (例如: https://www.youtube.com/watch?v=VIDEO_ID)
        import urllib.parse
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        video_id = query_params.get("v", [""])[0]
    else:
        # 如果无法识别格式，假设输入的就是视频ID
        video_id = url
    
    return video_id

class VideoDownloader:
    """处理YouTube视频下载的服务"""
    
    def __init__(self):
        """初始化下载器"""
        # 创建存储目录
        self.videos_dir = settings.VIDEOS_DIR
        self.audios_dir = settings.AUDIOS_DIR
        
        os.makedirs(self.videos_dir, exist_ok=True)
        os.makedirs(self.audios_dir, exist_ok=True)
        
        logger.info(f"本地存储目录初始化成功: {self.videos_dir}, {self.audios_dir}")
    
    def download_video(self, video_id: str, resolution: str = "720p", extract_audio: bool = True) -> Dict[str, Any]:
        """
        下载YouTube视频并存储到本地
        
        Args:
            video_id: YouTube视频ID
            resolution: 视频分辨率 (360p, 480p, 720p)
            extract_audio: 是否提取音频
            
        Returns:
            dict: 包含视频和音频URL的字典，以及视频元数据
        """
        logger.info(f"开始下载视频: {video_id}")
        
        try:
            # 创建临时目录
            temp_dir = Path(f"./temp_{video_id}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 设置分辨率
            max_height = 720  # 默认720p
            if resolution == "360p":
                max_height = 360
            elif resolution == "480p":
                max_height = 480
            
            logger.info(f"设置视频分辨率: {resolution} (最大高度: {max_height})")
            
            # 通用下载选项
            common_opts = {
                'noplaylist': True,
                'retries': 10,
                'fragment_retries': 10,
                'socket_timeout': 30,
                'nocheckcertificate': True,
                'ignoreerrors': False,
                'logtostderr': False,
                'quiet': False,
                'no_warnings': False,
                'default_search': 'auto',
                'source_address': '0.0.0.0',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                }
            }
            
            # 设置视频下载选项
            video_opts = {
                **common_opts,
                'format': f'bestvideo[height<={max_height}]/best[height<={max_height}]',
                'outtmpl': str(temp_dir / '%(id)s_video.%(ext)s'),
            }
            
            # 设置音频下载选项
            audio_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'outtmpl': str(temp_dir / '%(id)s_audio.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }],
            }
            
            # 下载视频和提取元数据
            video_path = None
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                
                # 提取元数据
                metadata = {
                    "title": info.get("title", ""),
                    "channel": info.get("channel", ""),
                    "upload_date": info.get("upload_date", ""),
                    "duration": info.get("duration", 0),
                    "view_count": info.get("view_count", 0),
                    "like_count": info.get("like_count", 0),
                    "categories": info.get("categories", []),
                    "tags": info.get("tags", []),
                    "description": info.get("description", ""),
                    "thumbnail": info.get("thumbnail", "")
                }
                
                # 获取下载的文件路径
                if 'requested_downloads' in info:
                    for download in info['requested_downloads']:
                        if download.get('filepath'):
                            video_path = download['filepath']
                
                # 如果没有找到路径，尝试从info中获取
                if not video_path and 'id' in info and 'ext' in info:
                    potential_path = temp_dir / f"{info['id']}_video.{info['ext']}"
                    if os.path.exists(potential_path):
                        video_path = potential_path
            
            # 如果需要提取音频
            audio_path = None
            if extract_audio:
                logger.info("下载音频...")
                with yt_dlp.YoutubeDL(audio_opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                    
                    # 检查音频文件路径
                    if 'requested_downloads' in info:
                        for download in info['requested_downloads']:
                            if download.get('filepath'):
                                audio_path = download['filepath']
                                break
                    
                    # 如果仍然没有找到，尝试查找.mp3文件
                    if not audio_path:
                        for file in os.listdir(temp_dir):
                            if file.endswith('.mp3') and '_audio' in file:
                                audio_path = temp_dir / file
                                break
            
            # 创建视频和音频的永久存储路径
            video_url = None
            audio_url = None
            
            if video_path:
                # 复制到永久存储目录
                video_filename = os.path.basename(video_path)
                permanent_video_path = self.videos_dir / f"{uuid.uuid4()}_{video_filename}"
                shutil.copy2(video_path, permanent_video_path)
                video_url = str(permanent_video_path.absolute())
                logger.info(f"视频已保存到本地: {permanent_video_path}")
            
            if audio_path:
                # 复制到永久存储目录
                audio_filename = os.path.basename(audio_path)
                permanent_audio_path = self.audios_dir / f"{uuid.uuid4()}_{audio_filename}"
                shutil.copy2(audio_path, permanent_audio_path)
                audio_url = str(permanent_audio_path.absolute())
                logger.info(f"音频已保存到本地: {permanent_audio_path}")
            
            # 清理临时文件
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    logger.info(f"已清理临时文件夹: {temp_dir}")
            except Exception as e:
                logger.error(f"清理临时文件失败: {str(e)}")
            
            return {
                "video_url": video_url,
                "audio_url": audio_url,
                "metadata": metadata
            }
        
        except Exception as e:
            logger.error(f"下载视频失败: {str(e)}")
            # 清理临时文件
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass
            raise

# 创建视频下载器实例
video_downloader = VideoDownloader()

def create_summary(user_id: str, summary_create: SummaryCreate) -> SummaryInDB:
    """
    创建新的视频摘要记录
    """
    # 提取视频ID
    video_id = extract_video_id(summary_create.video_url)
    
    # 创建摘要记录
    summary = SummaryInDB(
        id=str(uuid.uuid4()),
        user_id=user_id,
        video_id=video_id,
        video_url=summary_create.video_url,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        status="pending",  # 初始状态为等待处理
        summary="",  # 初始摘要为空
        error=None  # 初始无错误
    )
    
    # 保存到存储
    created_summary = summary_storage.create(summary)
    
    return created_summary

def get_summary_by_id(summary_id: str) -> Optional[SummaryInDB]:
    """根据ID获取摘要"""
    return summary_storage.get_by_id(summary_id)

def get_summaries_by_user_id(user_id: str) -> List[SummaryInDB]:
    """根据用户ID获取所有摘要"""
    return summary_storage.get_by_field("user_id", user_id)

def update_summary(summary_id: str, update_data: Dict[str, Any]) -> Optional[SummaryInDB]:
    """更新摘要"""
    return summary_storage.update_partial(summary_id, update_data)

def delete_summary(summary_id: str) -> bool:
    """删除摘要"""
    summary = get_summary_by_id(summary_id)
    if not summary:
        return False
    
    # 删除关键帧图像文件
    for keyframe in summary.keyframes:
        try:
            keyframe_path = Path(keyframe)
            if keyframe_path.exists():
                os.remove(keyframe_path)
        except Exception as e:
            logger.error(f"删除关键帧图像失败: {str(e)}")
    
    # 删除摘要记录
    return summary_storage.delete(summary_id) 