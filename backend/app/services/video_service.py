"""
改进的视频处理服务
支持双输入源、PySceneDetect场景检测（FFmpeg fallback）、阿里云OSS存储
"""
import logging
import uuid
import os
import subprocess
import json
import tempfile
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass

import yt_dlp

from ..core.logging import logger
from ..models.video import KeyframeInfo, VideoInfo


class AliyunVideoService:
    """改进的阿里云视频处理服务"""
    
    def __init__(self, temp_dir: str = None):
        """初始化视频服务"""
        if temp_dir:
            self.temp_dir = Path(temp_dir)
        else:
            self.temp_dir = Path(tempfile.gettempdir()) / "aliyun_video_service"
        
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"阿里云视频服务初始化完成，临时目录: {self.temp_dir}")
        
        # yt-dlp下载选项 (2025.11最新配置 - 绕过机器人检测)
        self.ytdl_opts = {
            # 基础配置
            'noplaylist': True,
            'retries': 10,
            'fragment_retries': 10,
            'extractor_retries': 3,
            'file_access_retries': 3,
            'socket_timeout': 60,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': False,
            'no_warnings': False,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            
            # 绕过限制配置
            'age_limit': None,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            
            # 2025.11 最新 HTTP 头配置（更真实的浏览器模拟）
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Sec-Ch-Ua': '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # YouTube 特定优化配置（2025.11更新 - 使用tv_downgraded客户端绕过bot检测）
            'extractor_args': {
                'youtube': {
                    # 多客户端降级策略：优先使用tv客户端，然后android，最后web
                    'player_client': ['tv_embedded', 'android', 'web'],
                    'skip': ['hls', 'dash'],  # 跳过某些流格式
                    'player_skip': ['webpage', 'configs'],  # 跳过网页解析，直接使用API
                }
            },
            
            # 禁用缓存以避免旧的bot检测数据
            'no_cache_dir': True,
        }
    
    def _generate_video_id(self) -> str:
        """生成唯一的视频ID"""
        return str(uuid.uuid4())
    
    def _extract_video_id_from_url(self, video_url: str) -> str:
        """从YouTube URL提取视频ID或生成哈希ID"""
        try:
            if "youtu.be/" in video_url:
                return video_url.split("youtu.be/")[-1].split("?")[0]
            elif "youtube.com/watch" in video_url:
                return video_url.split("v=")[-1].split("&")[0]
            else:
                return str(abs(hash(video_url)) % (10**8))
        except Exception:
            return self._generate_video_id()
    
    async def process_video_dual_source(self, 
                                      video_file: Optional[str] = None,
                                      youtube_url: Optional[str] = None) -> Dict[str, Any]:
        """
        双输入源视频处理
        
        Args:
            video_file: 用户上传的视频文件路径
            youtube_url: YouTube视频URL
            
        Returns:
            处理结果
        """
        if not video_file and not youtube_url:
            return {
                "status": "error",
                "error": "必须提供视频文件或YouTube URL",
                "video_id": None
            }
        
        video_id = self._generate_video_id()
        session_temp_dir = self.temp_dir / f"session_{video_id}"
        session_temp_dir.mkdir(exist_ok=True)
        
        try:
            logger.info(f"开始处理视频，ID: {video_id}")
            
            # 步骤1: 获取视频文件
            if youtube_url:
                logger.info(f"从YouTube下载视频: {youtube_url}")
                video_result = await self._download_from_youtube(youtube_url, session_temp_dir)
                if video_result["status"] != "success":
                    return video_result
                
                video_path = video_result["video_path"]
                video_metadata = video_result["metadata"]
                source_type = "youtube"
                original_url = youtube_url
                
            else:  # 用户上传文件
                logger.info(f"处理用户上传的视频: {video_file}")
                video_path = video_file
                video_metadata = await self._extract_video_metadata(video_path)
                source_type = "upload"
                original_url = None
            
            # 获取视频基本信息
            duration = video_metadata.get("duration", 0.0)
            title = video_metadata.get("title", Path(video_path).stem)
            
            # 步骤2: 上传原始视频到OSS
            from .oss_service import oss_service
            
            logger.info("上传视频到阿里云OSS...")
            video_oss_url = await oss_service.upload_video(video_path, video_id)
            
            if not video_oss_url:
                return {
                    "status": "error",
                    "error": "视频上传到OSS失败",
                    "video_id": video_id
                }
            
            # 步骤3: 提取关键帧（使用场景检测）
            logger.info("提取关键帧...")
            keyframes = await self.extract_keyframes_scene_detection(video_path, video_id, session_temp_dir)
            
            # 步骤4: 生成视频信息
            video_info = VideoInfo(
                video_id=video_id,
                title=title,
                duration=duration,
                oss_video_url=video_oss_url,
                upload_time=datetime.now(),
                source_type=source_type,
                original_url=original_url
            )
            
            return {
                "status": "success",
                "video_id": video_id,
                "video_info": video_info,
                "keyframes": keyframes,
                "video_metadata": video_metadata,
                "session_temp_dir": str(session_temp_dir)
            }
            
        except Exception as e:
            logger.exception(f"视频处理失败: {e}")
            return {
                "status": "error",
                "error": f"视频处理异常: {str(e)}",
                "video_id": video_id
            }
    
    async def _download_from_youtube(self, url: str, session_temp_dir: Path) -> Dict[str, Any]:
        """从YouTube下载视频（使用多种策略绕过bot检测）"""
        try:
            base_filename = session_temp_dir / "downloaded_video"
            
            # 配置yt-dlp选项（包含HTTP headers、重试机制等）
            opts = self.ytdl_opts.copy()
            opts['outtmpl'] = str(base_filename) + '.%(ext)s'
            opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            opts['merge_output_format'] = 'mp4'
            
            logger.info("开始从 YouTube 下载视频（使用多种策略绕过bot检测）...")
            logger.info(f"User-Agent: {opts['http_headers'].get('User-Agent', 'N/A')[:50]}...")
            
            # 使用Python API下载（尝试多种客户端策略）
            metadata = {}
            video_path = None
            download_success = False
            
            # 策略1: tv_embedded 客户端（最佳）
            try:
                logger.info("尝试策略1: tv_embedded 客户端...")
                opts_tv = opts.copy()
                opts_tv['extractor_args'] = {
                    'youtube': {
                        'player_client': ['tv_embedded'],
                        'skip': ['hls', 'dash'],
                        'player_skip': ['webpage', 'configs'],
                    }
                }
                with yt_dlp.YoutubeDL(opts_tv) as ydl:
                    info = ydl.extract_info(url, download=True)
                    metadata = info
                    download_success = True
                    logger.info(f"✅ tv_embedded 成功: {info.get('title', 'N/A')}")
            except Exception as e:
                logger.warning(f"⚠️ tv_embedded 失败: {str(e)[:150]}")
                
            # 策略2: android 客户端
            if not download_success:
                try:
                    logger.info("尝试策略2: android 客户端...")
                    opts_android = opts.copy()
                    opts_android['extractor_args'] = {
                        'youtube': {
                            'player_client': ['android'],
                            'skip': ['hls', 'dash'],
                        }
                    }
                    with yt_dlp.YoutubeDL(opts_android) as ydl:
                        info = ydl.extract_info(url, download=True)
                        metadata = info
                        download_success = True
                        logger.info(f"✅ android 成功: {info.get('title', 'N/A')}")
                except Exception as e:
                    logger.warning(f"⚠️ android 失败: {str(e)[:150]}")
            
            # 策略3: web_embedded 客户端
            if not download_success:
                try:
                    logger.info("尝试策略3: web_embedded 客户端...")
                    opts_web = opts.copy()
                    opts_web['extractor_args'] = {
                        'youtube': {
                            'player_client': ['web_embedded'],
                        }
                    }
                    with yt_dlp.YoutubeDL(opts_web) as ydl:
                        info = ydl.extract_info(url, download=True)
                        metadata = info
                        download_success = True
                        logger.info(f"✅ web_embedded 成功: {info.get('title', 'N/A')}")
                except Exception as e:
                    logger.error(f"❗ 所有策略均失败: {str(e)}")
                    raise Exception(f"YouTube 视频下载失败：{str(e)}")
            
            # 查找下载的视频文件
            for file_path in session_temp_dir.iterdir():
                if file_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
                    video_path = str(file_path)
                    break
            
            if video_path and os.path.exists(video_path):
                logger.info(f"YouTube视频下载成功: {video_path}")
                return {
                    "status": "success",
                    "video_path": video_path,
                    "metadata": metadata
                }
            else:
                error_msg = f"YouTube视频下载失败：找不到下载的文件"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = f"YouTube视频下载失败: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"YouTube下载异常: {str(e)}"
            logger.exception(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
    
    async def extract_keyframes_scene_detection(self, video_path: str, video_id: str, session_temp_dir: Path) -> List[KeyframeInfo]:
        """
        使用PySceneDetect进行场景检测提取关键帧（FFmpeg作为fallback）
        最多提取20帧
        
        Args:
            video_path: 视频文件路径
            video_id: 视频唯一标识
            session_temp_dir: 会话临时目录
            
        Returns:
            关键帧信息列表
        """
        if not os.path.exists(video_path):
            logger.error(f"视频文件不存在: {video_path}")
            return []
        
        try:
            # 创建关键帧输出目录
            keyframes_dir = session_temp_dir / "keyframes"
            keyframes_dir.mkdir(exist_ok=True)
            
            # 步骤1: 优先尝试PySceneDetect
            logger.info("尝试使用PySceneDetect进行场景检测...")
            scene_timestamps = await self._detect_scenes_with_pyscenedetect(video_path, threshold=27.0)
            
            # 步骤2: 如果PySceneDetect失败，使用FFmpeg fallback
            if not scene_timestamps:
                logger.info("回退到FFmpeg场景检测...")
                scene_timestamps = await self._detect_scenes_with_ffmpeg(video_path)
            
            # 步骤3: 如果两种方法都失败，使用均匀采样
            if not scene_timestamps:
                logger.warning("场景检测失败，使用均匀采样")
                scene_timestamps = await self._uniform_sampling(video_path, 10)
            
            # 限制最多20帧
            selected_scenes = scene_timestamps[:20]
            logger.info(f"选择了{len(selected_scenes)}个场景时间戳进行关键帧提取")
            
            keyframes = []
            from .oss_service import oss_service
            
            # 步骤4: 在每个场景时间戳提取帧
            for i, timestamp in enumerate(selected_scenes):
                frame_path = await self._extract_frame_at_timestamp(
                    video_path, timestamp, i, keyframes_dir
                )
                
                if frame_path and os.path.exists(frame_path):
                    # 上传到OSS
                    frame_oss_url = await oss_service.upload_keyframe(frame_path, video_id, i)
                    
                    keyframe_info = KeyframeInfo(
                        frame_id=i + 1,
                        timestamp=timestamp,
                        local_path=frame_path,
                        oss_image_url=frame_oss_url,
                        scene_description=f"场景{i + 1}"
                    )
                    keyframes.append(keyframe_info)
                    
                    logger.debug(f"提取关键帧 {i+1}/{len(selected_scenes)} 在 {timestamp:.2f}s")
            
            logger.info(f"成功提取{len(keyframes)}个关键帧")
            return keyframes
            
        except Exception as e:
            logger.exception(f"关键帧提取失败: {e}")
            return []
    
    async def _detect_scenes_with_pyscenedetect(self, video_path: str, threshold: float = 27.0) -> List[float]:
        """
        使用PySceneDetect进行高精度场景检测
        
        Args:
            video_path: 视频文件路径
            threshold: 场景检测阈值（默认27.0，范围0-100，值越小越敏感）
            
        Returns:
            场景变化时间戳列表
        """
        try:
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector
            
            logger.info(f"使用PySceneDetect进行场景检测，阈值: {threshold}")
            
            # 初始化视频管理器和场景管理器
            video_manager = VideoManager([video_path])
            scene_manager = SceneManager()
            
            # 添加内容检测器
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            
            # 开始场景检测
            video_manager.set_downscale_factor()  # 自动降采样以提升性能
            video_manager.start()
            
            # 执行检测
            scene_manager.detect_scenes(frame_source=video_manager)
            
            # 获取场景列表
            scene_list = scene_manager.get_scene_list()
            video_manager.release()
            
            # 提取每个场景的起始时间戳
            timestamps = []
            for scene in scene_list:
                start_time = scene[0].get_seconds()
                timestamps.append(start_time)
            
            # 过滤过于接近的时间戳（至少间隔2秒）
            filtered_timestamps = []
            last_timestamp = -999
            
            for timestamp in sorted(timestamps):
                if timestamp - last_timestamp >= 2.0:
                    filtered_timestamps.append(timestamp)
                    last_timestamp = timestamp
            
            if filtered_timestamps:
                logger.info(f"PySceneDetect检测到{len(filtered_timestamps)}个场景")
                return filtered_timestamps
            else:
                logger.warning("PySceneDetect未检测到明显场景变化")
                return []
                
        except ImportError:
            logger.warning("PySceneDetect库未安装，将使用FFmpeg fallback")
            return []
        except Exception as e:
            logger.exception(f"PySceneDetect场景检测失败: {e}")
            return []
    
    async def _detect_scenes_with_ffmpeg(self, video_path: str, threshold: float = 0.3) -> List[float]:
        """使用ffmpeg检测场景变化"""
        try:
            # ffmpeg场景检测命令
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-filter:v', f'select="gt(scene,{threshold})",metadata=print:file=-',
                '-vsync', 'vfr',
                '-f', 'null',
                '-'
            ]
            
            logger.debug(f"执行ffmpeg场景检测: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # 解析stderr中的场景变化信息
            timestamps = self._parse_scene_timestamps(stderr.decode())
            
            if timestamps:
                logger.info(f"检测到{len(timestamps)}个场景变化")
                return sorted(timestamps)
            else:
                logger.warning("未检测到明显的场景变化")
                return []
                
        except Exception as e:
            logger.exception(f"ffmpeg场景检测失败: {e}")
            return []
    
    def _parse_scene_timestamps(self, stderr_output: str) -> List[float]:
        """解析ffmpeg输出中的场景变化时间戳"""
        timestamps = []
        
        try:
            # 寻找frame metadata中的时间戳信息
            # ffmpeg输出格式例如：frame:123 pts:1234 pts_time:12.34
            pattern = r'pts_time:(\d+\.?\d*)'
            matches = re.findall(pattern, stderr_output)
            
            for match in matches:
                try:
                    timestamp = float(match)
                    timestamps.append(timestamp)
                except ValueError:
                    continue
            
            # 去重并排序
            unique_timestamps = sorted(list(set(timestamps)))
            
            # 过滤过于接近的时间戳（至少间隔2秒）
            filtered_timestamps = []
            last_timestamp = -999
            
            for timestamp in unique_timestamps:
                if timestamp - last_timestamp >= 2.0:
                    filtered_timestamps.append(timestamp)
                    last_timestamp = timestamp
            
            return filtered_timestamps
            
        except Exception as e:
            logger.error(f"解析场景时间戳失败: {e}")
            return []
    
    async def _uniform_sampling(self, video_path: str, num_frames: int) -> List[float]:
        """均匀采样作为场景检测的fallback"""
        try:
            # 获取视频时长
            metadata = await self._extract_video_metadata(video_path)
            duration = metadata.get("duration", 0)
            
            if duration <= 0:
                return []
            
            # 均匀分布的时间戳
            timestamps = []
            for i in range(num_frames):
                timestamp = (i + 0.5) * duration / num_frames
                timestamps.append(timestamp)
            
            logger.info(f"生成{len(timestamps)}个均匀采样时间戳")
            return timestamps
            
        except Exception as e:
            logger.error(f"均匀采样失败: {e}")
            return []
    
    async def _extract_frame_at_timestamp(self, video_path: str, timestamp: float, 
                                        frame_index: int, output_dir: Path) -> Optional[str]:
        """在指定时间戳提取帧"""
        try:
            frame_filename = f"frame_{frame_index:03d}_{timestamp:.2f}s.jpg"
            frame_path = output_dir / frame_filename
            
            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),
                '-i', video_path,
                '-vframes', '1',
                '-q:v', '2',
                '-y',
                str(frame_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0 and frame_path.exists():
                return str(frame_path)
            else:
                logger.error(f"帧提取失败，时间戳: {timestamp}")
                return None
                
        except Exception as e:
            logger.exception(f"提取帧异常: {e}")
            return None
    
    async def _extract_video_metadata(self, video_path: str) -> Dict[str, Any]:
        """提取视频metadata"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                metadata = json.loads(stdout.decode())
                
                # 提取关键信息
                format_info = metadata.get("format", {})
                video_stream = None
                
                for stream in metadata.get("streams", []):
                    if stream.get("codec_type") == "video":
                        video_stream = stream
                        break
                
                return {
                    "title": Path(video_path).stem,
                    "duration": float(format_info.get("duration", 0)),
                    "size": int(format_info.get("size", 0)),
                    "format_name": format_info.get("format_name", ""),
                    "width": video_stream.get("width", 0) if video_stream else 0,
                    "height": video_stream.get("height", 0) if video_stream else 0,
                    "fps": eval(video_stream.get("r_frame_rate", "0/1")) if video_stream else 0,
                    "codec": video_stream.get("codec_name", "") if video_stream else ""
                }
            else:
                logger.error(f"ffprobe提取metadata失败: {stderr.decode()}")
                return {}
                
        except Exception as e:
            logger.exception(f"提取video metadata异常: {e}")
            return {}
    
    def cleanup_session(self, session_temp_dir: str):
        """清理会话临时目录"""
        if session_temp_dir and os.path.exists(session_temp_dir):
            try:
                import shutil
                shutil.rmtree(session_temp_dir)
                logger.info(f"已清理会话目录: {session_temp_dir}")
            except Exception as e:
                logger.error(f"清理会话目录失败 {session_temp_dir}: {e}")


# 创建单例实例
video_service = AliyunVideoService()