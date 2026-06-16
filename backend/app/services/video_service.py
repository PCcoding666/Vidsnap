"""
改进的视频处理服务
仅支持本地上传视频、PySceneDetect场景检测（FFmpeg fallback）、可选阿里云OSS存储
"""
import uuid
import os
import json
import tempfile
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from ..core.logging import logger
from ..core.config import settings
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
    
    def _generate_video_id(self) -> str:
        """生成唯一的视频ID"""
        return str(uuid.uuid4())
    
    async def process_uploaded_video(self, video_file: Optional[str] = None) -> Dict[str, Any]:
        """
        处理用户上传的视频文件。
        
        Args:
            video_file: 用户上传的视频文件路径
            
        Returns:
            处理结果
        """
        if not video_file:
            return {
                "status": "error",
                "error": "必须提供视频文件",
                "video_id": None
            }
        
        video_id = self._generate_video_id()
        session_temp_dir = self.temp_dir / f"session_{video_id}"
        session_temp_dir.mkdir(exist_ok=True)
        
        try:
            logger.info(f"开始处理视频，ID: {video_id}")
            
            # 步骤1: 获取上传视频的基础信息
            logger.info(f"处理用户上传的视频: {video_file}")
            video_path = video_file
            video_metadata = await self._extract_video_metadata(video_path)
            source_type = "upload"
            original_url = None
            
            # 获取视频基本信息
            duration = video_metadata.get("duration", 0.0)
            title = video_metadata.get("title", Path(video_path).stem)
            
            # 步骤2: 可选上传原始视频到OSS。Slim 本地开发不应依赖云存储。
            video_oss_url = None
            if settings.ENABLE_OSS_UPLOADS:
                from .oss_service import oss_service

                logger.info("上传视频到阿里云OSS...")
                video_oss_url = await oss_service.upload_video(video_path, video_id)

                if not video_oss_url:
                    logger.warning("视频上传到OSS失败，将继续使用本地视频文件处理")
            else:
                logger.info("跳过原始视频OSS上传，使用本地视频文件处理")
            
            # 步骤3: 生成视频信息（关键帧提取延迟到 Pipeline 层并发执行）
            video_info = VideoInfo(
                video_id=video_id,
                title=title,
                duration=duration,
                oss_video_url=video_oss_url,
                upload_time=datetime.now(),
                source_type=source_type,
                original_url=original_url
            )
            
            logger.info(f"视频处理完成（不包含关键帧提取）: {video_path}")
            
            return {
                "status": "success",
                "video_id": video_id,
                "video_info": video_info,
                "video_path": video_path,
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
    
    async def extract_keyframes_scene_detection(self, video_path: str, video_id: str, session_temp_dir: Path) -> List[KeyframeInfo]:
        """
        使用PySceneDetect进行场景检测提取关键帧 - 已禁用
        
        安全更新: 关键帧提取功能已禁用，系统改为基于逐字稿的纯文本分析
        
        Args:
            video_path: 视频文件路径
            video_id: 视频唯一标识
            session_temp_dir: 会话临时目录
            
        Returns:
            空列表（功能已禁用）
        """
        logger.info(f"关键帧提取功能已禁用，返回空列表 (video_id={video_id})")
        return []
        
        # ===== 以下代码已禁用，保留供参考 =====
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
