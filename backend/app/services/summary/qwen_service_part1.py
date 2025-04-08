import os
import json
import logging
import requests
import base64
from typing import Optional, List, Dict, Any, Tuple, Union
import cv2
import numpy as np
from PIL import Image
import io
import tempfile
from pathlib import Path
import uuid
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError

from app.core.config import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义关键帧提取方法枚举
KEYFRAME_METHODS = {
    "uniform": "均匀分段采样",
    "interval": "固定时间间隔采样",
    "scene": "场景检测采样"
}

# GCS 客户端 (假设已通过环境变量 GOOGLE_APPLICATION_CREDENTIALS 配置认证)
try:
    # 检查是否有明确的凭证路径
    gcs_credentials_path = getattr(settings, 'GCS_CREDENTIALS_PATH', None)
    if gcs_credentials_path and os.path.exists(gcs_credentials_path):
        logger.info(f"Using GCS credentials from path: {gcs_credentials_path}")
        storage_client = storage.Client.from_service_account_json(gcs_credentials_path)
    else:
        logger.info("GCS_CREDENTIALS_PATH not set or file not found, using Application Default Credentials.")
        storage_client = storage.Client()

    GCS_BUCKET_NAME = settings.GCS_BUCKET_NAME
    if not GCS_BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME must be set in settings or environment variables")
    gcs_bucket = storage_client.bucket(GCS_BUCKET_NAME)
    logger.info(f"Google Cloud Storage client initialized for bucket: {GCS_BUCKET_NAME}")
except (ImportError, ValueError, GoogleAPIError) as e:
    logger.warning(f"Failed to initialize Google Cloud Storage client: {e}. GCS upload will be unavailable.")
    storage_client = None
    gcs_bucket = None

def upload_to_gcs(source_file_path: str, destination_blob_name: str) -> Optional[str]:
    """将本地文件上传到 GCS 并返回公共 URL 或 GCS URI"""
    if not gcs_bucket or not storage_client:
        logger.error("GCS client not initialized. Cannot upload file.")
        return None

    try:
        blob = gcs_bucket.blob(destination_blob_name)
        # 设置 content_type 以便浏览器正确显示
        content_type = 'image/jpeg' if source_file_path.lower().endswith(('.jpg', '.jpeg')) else None
        blob.upload_from_filename(source_file_path, content_type=content_type)
        logger.info(f"File {source_file_path} uploaded to gs://{GCS_BUCKET_NAME}/{destination_blob_name}")

        # 获取存储桶的 IAM 配置以检查是否为 Uniform 访问
        is_uniform_access = False
        try:
            iam_config = gcs_bucket.iam_configuration
            is_uniform_access = iam_config.uniform_bucket_level_access_enabled
            logger.info(f"Bucket uniform access enabled: {is_uniform_access}")
        except Exception as iam_err:
            logger.warning(f"Could not determine bucket access mode: {iam_err}. Assuming non-uniform.")

        if is_uniform_access:
            # 对于 Uniform Access，不能调用 make_public()。
            # 假设已通过 IAM 设置公开访问权限。直接构造 URL。
            public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"
            logger.info(f"Uniform access enabled. Constructed public URL (assuming IAM allows public access): {public_url}")
            # 可以在这里添加检查 blob 是否存在的逻辑
            # try:
            #     if gcs_bucket.get_blob(destination_blob_name):
            #         logger.info(f"Blob {destination_blob_name} confirmed to exist.")
            #         return public_url
            #     else:
            #         logger.error(f"Blob {destination_blob_name} not found after upload (uniform access).")
            #         return None
            # except Exception as check_err:
            #     logger.error(f"Error checking blob existence (uniform access): {check_err}")
            #     return None # 或者返回 public_url，让调用者处理潜在的 403
            return public_url # 直接返回构造的 URL
        else:
            # 对于非 Uniform Access (Fine-grained)，尝试调用 make_public()
            try:
                blob.make_public()
                public_url = blob.public_url
                logger.info(f"Successfully made blob public (fine-grained access): {public_url}")
                return public_url
            except GoogleAPIError as e:
                logger.error(f"Failed to make blob public (fine-grained access): {e}")
                # 返回 GCS URI 表示上传成功但未公开
                gcs_uri = f"gs://{GCS_BUCKET_NAME}/{destination_blob_name}"
                logger.warning(f"Blob uploaded but could not be made public. Returning GCS URI: {gcs_uri}")
                return gcs_uri

    except GoogleAPIError as e:
        logger.error(f"GCS Upload Error: Failed to upload {source_file_path} to {destination_blob_name}: {e}")
        return None
    except FileNotFoundError:
        logger.error(f"GCS Upload Error: Local file not found: {source_file_path}")
        return None
    except Exception as e:
        logger.error(f"GCS Upload Error: An unexpected error occurred during upload: {e}", exc_info=True)
        return None

class QwenService:
    """千问API服务 (确保在应用启动时尽早调用 load_dotenv())"""
    
    def __init__(self):
        """初始化千问API服务"""
        # 从环境变量获取API密钥
        self.api_key = settings.QWEN_API_KEY
        
        if not self.api_key:
            logger.warning("未设置QWEN_API_KEY环境变量，千问API服务不可用")
            self.available = False
        else:
            self.available = True
            logger.info("千问API服务初始化完成")
        
        # 使用OpenAI兼容的API端点
        self.api_base = settings.QWEN_API_BASE
        
        # 模型名称
        self.model = settings.QWEN_MODEL
        
        # 启用高分辨率图像
        self.vl_high_resolution_images = True
        # 修改token分配比例为80%
        self.max_tokens = 30720  # qwen-vl-max的最大token限制
        # 每张图片的token消耗 (高分辨率模式下为2118，低分辨率模式下为1227)
        self.image_token_cost = 2118 if self.vl_high_resolution_images else 1227
        # 修改为允许图片占用80%的token
        self.max_images = int(self.max_tokens * 0.8 / self.image_token_cost)
        
        logger.info(f"千问API配置: 模型={self.model}, 高分辨率图像={self.vl_high_resolution_images}, 最大图片数量={self.max_images}")
        
        # 请求头
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 请求超时时间（秒）
        self.timeout = 120
    
    def is_available(self) -> bool:
        """检查千问API服务是否可用"""
        return self.available and self.api_key is not None
    
    def extract_key_frames(self, video_path: str, method: str = "uniform",
                           num_frames: int = 5, interval_seconds: int = 10) -> List[str]:
        """
        从视频中提取关键帧, 上传到 GCS 并返回其公共 URL

        Args:
            video_path: 视频文件路径
            method: 提取方法 ("uniform"=均匀分段, "interval"=固定时间间隔, "scene"=场景检测)
            num_frames: 要提取的关键帧数量（适用于均匀分段和场景检测方法）
            interval_seconds: 固定时间间隔（秒）（适用于固定时间间隔方法）

        Returns:
            List[str]: 包含上传到 GCS 的图像公共 URL (或 GCS URI) 的列表
        """
        logger.info(f"开始从视频提取关键帧并上传到 GCS: {video_path}, 方法: {method}")

        # 去除文件前缀 (如果有)
        if video_path.startswith("file://"):
            video_path = video_path[7:]

        # 根据不同的提取方法调用相应的函数
        keyframe_local_paths: List[str] = []
        if method == "uniform":
            keyframe_local_paths = self._extract_uniform_frames(video_path, num_frames)
        elif method == "interval":
            keyframe_local_paths = self._extract_interval_frames(video_path, interval_seconds)
        elif method == "scene":
            keyframe_local_paths = self._extract_scene_frames(video_path, num_frames)
        else:
            logger.warning(f"未知的关键帧提取方法: {method}，使用默认的均匀分段方法")
            keyframe_local_paths = self._extract_uniform_frames(video_path, num_frames)

        # 上传关键帧到 GCS
        gcs_urls: List[str] = []
        if not keyframe_local_paths:
            logger.warning("没有提取到关键帧文件路径")
            return []

        logger.info(f"提取到 {len(keyframe_local_paths)} 个本地关键帧，开始上传到 GCS...")

        for local_path in keyframe_local_paths:
            if not os.path.exists(local_path):
                logger.warning(f"本地关键帧文件不存在，跳过上传: {local_path}")
                continue

            # 创建一个在 GCS 中唯一的目标名称
            destination_blob_name = f"keyframes/{uuid.uuid4()}_{os.path.basename(local_path)}"

            gcs_url = upload_to_gcs(local_path, destination_blob_name)
            if gcs_url:
                # 只添加有效的 URL (http/https 或 gs://)
                if gcs_url.startswith(("http", "gs://")):
                     gcs_urls.append(gcs_url)
                else:
                     logger.error(f"上传成功但返回了无效的 URL 格式: {gcs_url} for {local_path}")
            else:
                logger.error(f"上传失败: {local_path}")

            # 上传后删除本地文件以节省空间
            try:
                if os.path.exists(local_path): # 再次检查以防万一
                    os.remove(local_path)
                    # logger.info(f"已删除本地临时关键帧文件: {local_path}")
            except OSError as e:
                logger.error(f"删除本地关键帧文件失败: {local_path}, Error: {e}")

        logger.info(f"成功上传 {len(gcs_urls)} 个关键帧到 GCS (可能包含 GCS URIs)")
        return gcs_urls

    def _extract_uniform_frames(self, video_path: str, num_frames: int = 5) -> List[str]:
        """
        从视频中均匀提取指定数量的帧, 保存到本地并返回文件路径列表

        Args:
            video_path: 视频文件路径
            num_frames: 要提取的关键帧数量

        Returns:
            List[str]: 包含本地保存的关键帧文件路径的列表
        """
        adaptive_num_frames = min(num_frames, self.max_images)
        logger.info(f"使用均匀分段方法提取关键帧, 原始帧数: {num_frames}, 基于token限制调整后: {adaptive_num_frames}")

        local_paths = [] # 存储本地文件路径
        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"无法打开视频文件: {video_path}")
                return []

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            logger.info(f"视频信息 - 总帧数: {total_frames}, FPS: {fps:.2f}, 时长: {duration:.2f}秒")

            if total_frames <= 0 or duration <=0: # 增加检查
                 logger.error(f"视频文件似乎无效或无法读取帧数/时长: {video_path}")
                 if cap: cap.release()
                 return []

            if total_frames <= adaptive_num_frames:
                frame_indices = list(range(total_frames))
            else:
                segment_length = duration / adaptive_num_frames
                # 确保 segment_length 大于 0
                if segment_length <= 0:
                     logger.error(f"计算出的段长度无效: {segment_length}, 无法提取帧")
                     if cap: cap.release()
                     return []
                frame_indices = [int((i + 0.5) * segment_length * fps) for i in range(adaptive_num_frames)]
            logger.info(f"计划提取的帧索引: {frame_indices}")

            # 确保 KEYFRAMES_DIR 存在
            keyframe_dir_path = Path(settings.KEYFRAMES_DIR)
            keyframe_dir_path.mkdir(parents=True, exist_ok=True)

            for idx in frame_indices:
                # 检查索引有效性
                if idx < 0 or idx >= total_frames:
                    logger.warning(f"计算出的帧索引 {idx} 超出范围 [0, {total_frames-1}]，跳过")
                    continue

                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"无法读取第{idx}帧，跳过")
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)

                keyframe_filename = f"{uuid.uuid4()}_frame_{idx}.jpg"
                keyframe_path = os.path.join(str(keyframe_dir_path), keyframe_filename)

                try:
                    pil_image.save(keyframe_path, format="JPEG", quality=95)
                    local_paths.append(keyframe_path)
                    # logger.info(f"成功提取并保存第{idx}帧到: {keyframe_path}")
                except Exception as save_err:
                    logger.error(f"保存第{idx}帧到本地失败: {save_err}")

            logger.info(f"成功提取并保存 {len(local_paths)} 个本地关键帧")
            return local_paths

        except Exception as e:
            logger.error(f"提取均匀关键帧时出错: {str(e)}")
            # 清理可能已创建的文件
            for path in local_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            return []
        finally:
             if cap and cap.isOpened():
                 cap.release()

    def _extract_interval_frames(self, video_path: str, interval_seconds: int = 10) -> List[str]:
        """
        按照固定时间间隔从视频中提取帧, 保存到本地并返回文件路径列表

        Args:
            video_path: 视频文件路径
            interval_seconds: 提取帧的时间间隔（秒）

        Returns:
            List[str]: 包含本地保存的关键帧文件路径的列表
        """
        logger.info(f"使用固定时间间隔方法提取关键帧, 间隔: {interval_seconds}秒")
        local_paths = []
        cap = None # 初始化 cap 变量

        try:
            # 尝试使用 ffmpeg 获取更准确的时长和帧信息 (如果可用)
            duration = None
            fps = None
            total_frames = None
            try:
                import ffmpeg
                probe = ffmpeg.probe(video_path)
                video_info = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                if video_info:
                    duration = float(probe['format']['duration'])
                    if 'avg_frame_rate' in video_info and '/' in video_info['avg_frame_rate']:
                        num, den = map(int, video_info['avg_frame_rate'].split('/'))
                        fps = num / den if den != 0 else 30 # Default fps
                    elif 'r_frame_rate' in video_info and '/' in video_info['r_frame_rate']:
                         num, den = map(int, video_info['r_frame_rate'].split('/'))
                         fps = num / den if den != 0 else 30
                    else:
                        fps = 30 # Default fps
                    total_frames = int(duration * fps)
                    logger.info(f"视频信息 (ffmpeg) - 时长: {duration:.2f}s, FPS: {fps:.2f}, 估算总帧数: {total_frames}")
                else:
                     logger.warning("无法使用 ffmpeg 获取视频流信息")
            except ImportError:
                logger.warning("ffmpeg-python 未安装，将使用 OpenCV 获取视频信息")
            except Exception as ff_err:
                logger.warning(f"使用 ffmpeg 获取信息时出错: {ff_err}")

            # 如果 ffmpeg 失败或不可用，回退到 OpenCV
            if duration is None or fps is None or total_frames is None or duration <= 0 or fps <= 0:
                logger.info("回退到 OpenCV 获取视频信息")
                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    logger.error(f"无法打开视频文件 (OpenCV): {video_path}")
                    return []
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                _fps = cap.get(cv2.CAP_PROP_FPS)
                fps = _fps if _fps and _fps > 0 else 30 # Default fps
                duration = total_frames / fps if fps > 0 and total_frames > 0 else 0
                cap.release() # 获取信息后释放
                logger.info(f"视频信息 (OpenCV) - 总帧数: {total_frames}, FPS: {fps:.2f}, 时长: {duration:.2f}秒")

            if duration <= 0 or fps <= 0 or total_frames <= 0:
                 logger.error(f"无法获取有效的视频时长/FPS/总帧数: {video_path}")
                 return []

            # 计算需要提取的时间点
            timestamps = []
            current_time = 0
            while current_time < duration:
                timestamps.append(current_time)
                current_time += interval_seconds

            # 基于 token 限制调整时间点数量
            if len(timestamps) > self.max_images:
                step = len(timestamps) / self.max_images
                selected_timestamps = []
                for i in range(self.max_images):
                    idx = min(int(i * step), len(timestamps) - 1)
                    selected_timestamps.append(timestamps[idx])
                timestamps = selected_timestamps
                logger.info(f"基于token限制调整提取时间点数量至: {len(timestamps)}")

            logger.info(f"计划提取的时间点: {[f'{t:.2f}s' for t in timestamps]} (调整后总数: {len(timestamps)})")

            # 确保 KEYFRAMES_DIR 存在
            keyframe_dir_path = Path(settings.KEYFRAMES_DIR)
            keyframe_dir_path.mkdir(parents=True, exist_ok=True)

            # 重新打开视频文件以提取帧
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                 logger.error(f"无法重新打开视频文件以提取帧: {video_path}")
                 return []

            for t in timestamps:
                frame_idx = int(t * fps)
                # 确保帧索引有效
                if frame_idx < 0 or frame_idx >= total_frames:
                    logger.warning(f"计算出的时间点 {t:.2f}s 对应的帧索引 {frame_idx} 超出范围 [0, {total_frames-1}]，跳过")
                    continue

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"无法读取时间点 {t:.2f}s (帧 {frame_idx}) 对应的帧，跳过")
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)

                keyframe_filename = f"{uuid.uuid4()}_interval_{t:.2f}s.jpg"
                keyframe_path = os.path.join(str(keyframe_dir_path), keyframe_filename)

                try:
                    pil_image.save(keyframe_path, format="JPEG", quality=95)
                    local_paths.append(keyframe_path)
                    # logger.info(f"成功提取并保存时间点 {t:.2f}s 的帧到: {keyframe_path}")
                except Exception as save_err:
                    logger.error(f"保存时间点 {t:.2f}s 的帧到本地失败: {save_err}")

            logger.info(f"成功提取并保存 {len(local_paths)} 个本地关键帧 (固定间隔)")
            return local_paths

        except Exception as e:
            logger.error(f"提取固定间隔关键帧时出错: {str(e)}")
            # 清理可能已创建的文件
            for path in local_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            return []
        finally:
             if cap and cap.isOpened():
                 cap.release()

    def _extract_scene_frames(self, video_path: str, num_frames: int = 5) -> List[str]:
        """
        使用场景检测提取关键帧, 保存到本地并返回文件路径列表
        注意: 这需要 scenedetect 库 (`pip install scenedetect[opencv]`)

        Args:
            video_path: 视频文件路径
            num_frames: 期望的最大关键帧数量 (实际数量可能因场景变化而不同)

        Returns:
            List[str]: 包含本地保存的关键帧文件路径的列表
        """
        adaptive_num_frames = min(num_frames, self.max_images)
        logger.info(f"使用场景检测方法提取关键帧, 期望最大帧数: {num_frames}, 基于token限制调整后: {adaptive_num_frames}")
        local_paths = []
        video = None # 初始化 video

        try:
            try:
                 from scenedetect import open_video, SceneManager
                 from scenedetect.detectors import ContentDetector
                 from scenedetect.scene_manager import save_images
            except ImportError:
                 logger.error("场景检测需要 'scenedetect' 库。请运行 'pip install scenedetect[opencv]'")
                 logger.warning("回退到均匀采样方法")
                 return self._extract_uniform_frames(video_path, adaptive_num_frames) # 回退

            video = open_video(video_path)
            if not video:
                 logger.error(f"无法使用 scenedetect 打开视频: {video_path}")
                 return []

            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector()) # 使用内容变化检测器
            scene_manager.detect_scenes(video=video, show_progress=False) # 禁用进度条避免干扰日志
            scene_list = scene_manager.get_scene_list()

            logger.info(f"检测到 {len(scene_list)} 个场景")

            if not scene_list:
                logger.warning("未检测到任何场景，将回退到均匀采样")
                if video: video.release()
                return self._extract_uniform_frames(video_path, adaptive_num_frames)

            # 确保 KEYFRAMES_DIR 存在
            keyframe_dir_path = Path(settings.KEYFRAMES_DIR)
            keyframe_dir_path.mkdir(parents=True, exist_ok=True)

            # 从每个场景中选择一个代表性帧 (通常是中间帧)
            num_scenes_to_sample = min(len(scene_list), adaptive_num_frames)
            if num_scenes_to_sample <= 0: # 如果调整后为0，则不提取
                 logger.warning("调整后的采样场景数为0，不提取场景关键帧")
                 if video: video.release()
                 return []

            # 计算要跳过的场景数，以均匀选择
            step = len(scene_list) / num_scenes_to_sample
            selected_scene_indices = [int(i * step) for i in range(num_scenes_to_sample)]

            logger.info(f"计划从 {num_scenes_to_sample} 个场景中采样关键帧, 索引: {selected_scene_indices}")

            frame_numbers_to_save = []
            scene_map = {} # 记录帧号对应的场景索引
            for i in selected_scene_indices:
                 scene = scene_list[i]
                 # 选择场景中间的帧
                 start_frame = scene[0].frame_num
                 end_frame = scene[1].frame_num
                 if start_frame >= end_frame: # 处理单帧场景或无效场景
                      middle_frame = start_frame
                 else:
                      middle_frame = start_frame + (end_frame - start_frame) // 2
                 frame_numbers_to_save.append(middle_frame)
                 scene_map[middle_frame] = i # 记录该帧属于哪个场景索引

            # 去重帧号 (虽然理论上中间帧不应重复，但以防万一)
            frame_numbers_to_save = sorted(list(set(frame_numbers_to_save)))
            logger.info(f"计划保存的帧号 (去重后): {frame_numbers_to_save}")

            if not frame_numbers_to_save:
                 logger.warning("计算后没有需要保存的帧号")
                 if video: video.release()
                 return []

            # 使用 save_images 函数来高效地保存指定帧号的图像
            # 文件名模板使用 UUID 保证唯一性，稍后重命名
            temp_name_template = f"{uuid.uuid4()}_scenedetect_$FRAME_NUMBER"
            try:
                saved_images_map = save_images(
                     scene_list=[], # 传递空列表，因为我们提供了特定的帧号
                     video=video,
                     num_images=len(frame_numbers_to_save), # 与 frame_numbers 匹配
                     frame_source=frame_numbers_to_save, # 指定要保存的帧号
                     output_dir=str(keyframe_dir_path),
                     image_name_template=temp_name_template,
                     encoder_params={'quality': 95} # 设置JPEG质量
                )
            except Exception as save_img_err:
                 logger.error(f"scenedetect save_images 失败: {save_img_err}")
                 if video: video.release()
                 # 清理已创建的临时文件
                 for f_num in frame_numbers_to_save:
                     temp_file = keyframe_dir_path / f"{temp_name_template.replace('$FRAME_NUMBER', str(f_num))}.jpg"
                     if temp_file.exists():
                         try: os.remove(temp_file) 
                         except OSError: pass
                 return []

            # 重命名并收集路径
            for frame_num, paths in saved_images_map.items():
                if paths:
                    original_path_str = paths[0]
                    original_path = Path(original_path_str)
                    scene_index = scene_map.get(frame_num, 'unknown') # 获取对应的场景索引
                    new_filename = f"{uuid.uuid4()}_scene_{scene_index}_frame_{frame_num}.jpg"
                    new_path = keyframe_dir_path / new_filename
                    try:
                        original_path.rename(new_path)
                        local_paths.append(str(new_path))
                        # logger.info(f"成功提取场景 {scene_index} 的关键帧并保存到: {new_path}")
                    except OSError as rename_err:
                        logger.error(f"重命名场景帧失败: {rename_err}, 保留原始路径: {original_path_str}")
                        local_paths.append(original_path_str) # 保留原始路径
                else:
                     logger.warning(f"save_images 未能保存帧 {frame_num}")

            logger.info(f"成功提取并保存 {len(local_paths)} 个本地关键帧 (场景检测)")
            return local_paths

        except Exception as e:
            logger.error(f"提取场景关键帧时出错: {str(e)}")
            # 清理可能已创建的文件
            for path in local_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                         pass
            return []
        finally:
             if video: # 确保释放 video 对象
                  try:
                      video.release()
                  except Exception as release_err:
                       logger.warning(f"释放 scenedetect video 对象时出错: {release_err}") 