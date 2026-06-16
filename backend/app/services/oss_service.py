"""
阿里云OSS存储服务
处理视频、音频、关键帧图片和metadata的上传和访问
"""
import logging
import mimetypes
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import oss2
from pathlib import Path

from ..core.logging import logger
from ..core.config import settings


class AliyunOSSService:
    """阿里云OSS存储服务"""
    
    def __init__(self):
        """初始化OSS服务"""
        if not settings.ENABLE_OSS_UPLOADS:
            self.access_key_id = ""
            self.access_key_secret = ""
            self.endpoint = ""
            self.bucket_name = ""
            self.available = False
            self.auth = None
            self.bucket = None
            logger.info("OSS上传已禁用 (ENABLE_OSS_UPLOADS=false)")
            return

        # 从配置获取阿里云OSS配置
        self.access_key_id = settings.ALIYUN_ACCESS_KEY_ID
        self.access_key_secret = settings.ALIYUN_ACCESS_KEY_SECRET
        self.endpoint = self._normalize_endpoint(settings.ALIYUN_OSS_ENDPOINT)
        self.bucket_name = settings.ALIYUN_OSS_BUCKET
        
        # 检查必要的配置
        if not all([self.access_key_id, self.access_key_secret, self.endpoint, self.bucket_name]):
            logger.warning("阿里云OSS配置不完整，请设置环境变量：ALIYUN_ACCESS_KEY_ID, ALIYUN_ACCESS_KEY_SECRET, ALIYUN_OSS_ENDPOINT, ALIYUN_OSS_BUCKET")
            self.available = False
            self.auth = None
            self.bucket = None
        else:
            try:
                # 初始化OSS连接
                self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)
                self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)
                self.available = True
                logger.info(f"阿里云OSS服务初始化成功，Bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"阿里云OSS初始化失败: {e}")
                self.available = False
                self.auth = None
                self.bucket = None
    
    def is_available(self) -> bool:
        """检查OSS服务是否可用"""
        return self.available

    def _normalize_endpoint(self, endpoint: str) -> str:
        """规范化OSS endpoint，oss2 SDK 需要包含协议。"""
        endpoint = (endpoint or "").strip().rstrip("/")
        if not endpoint:
            return ""
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"https://{endpoint}"

    def _public_url(self, object_key: str) -> str:
        """生成未签名的标准OSS访问URL。"""
        clean_endpoint = self.endpoint.replace('https://', '').replace('http://', '')
        return f"https://{self.bucket_name}.{clean_endpoint}/{object_key}"

    def _access_url(self, object_key: str) -> str:
        """生成给外部服务读取的URL，默认使用签名URL兼容私有Bucket。"""
        if settings.OSS_USE_SIGNED_URLS:
            return self.bucket.sign_url(
                "GET",
                object_key,
                settings.OSS_SIGNED_URL_EXPIRES_SECONDS,
                slash_safe=True
            )
        return self._public_url(object_key)

    def _content_type_for_file(self, file_path: str, default: str = "application/octet-stream") -> str:
        """根据文件名推断Content-Type。"""
        suffix = Path(file_path).suffix.lower()
        explicit_types = {
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".opus": "audio/ogg",
            ".wav": "audio/wav",
        }
        if suffix in explicit_types:
            return explicit_types[suffix]
        content_type, _ = mimetypes.guess_type(file_path)
        return content_type or default
    
    def _generate_object_key(self, video_id: str, file_type: str, filename: str) -> str:
        """生成OSS对象键"""
        timestamp = datetime.now().strftime("%Y%m%d")
        return f"videos/{timestamp}/{video_id}/{file_type}/{filename}"
    
    async def upload_video(self, video_path: str, video_id: str) -> Optional[str]:
        """
        上传视频文件到OSS
        
        Args:
            video_path: 本地视频文件路径
            video_id: 视频唯一标识
            
        Returns:
            OSS访问URL或None
        """
        if not self.is_available():
            logger.error("OSS服务不可用")
            return None
        
        try:
            filename = Path(video_path).name
            object_key = self._generate_object_key(video_id, "original", filename)
            
            logger.info(f"开始上传视频文件: {video_path} -> {object_key}")
            
            headers = {"Content-Type": self._content_type_for_file(video_path, "video/webm")}

            # 上传文件
            with open(video_path, 'rb') as fileobj:
                self.bucket.put_object(object_key, fileobj, headers=headers)
            
            url = self._access_url(object_key)
            logger.info(f"视频上传成功: {object_key}")
            
            return url
            
        except Exception as e:
            logger.error(f"视频上传失败: {e}")
            return None
    
    async def upload_audio(self, audio_path: str, video_id: str) -> Optional[str]:
        """
        上传音频文件到OSS
        
        Args:
            audio_path: 本地音频文件路径
            video_id: 视频唯一标识
            
        Returns:
            OSS访问URL或None
        """
        if not self.is_available():
            logger.error("OSS服务不可用")
            return None
        
        try:
            filename = Path(audio_path).name
            object_key = self._generate_object_key(video_id, "audio", filename)
            
            logger.info(f"开始上传音频文件: {audio_path} -> {object_key}")
            
            headers = {"Content-Type": self._content_type_for_file(audio_path, "audio/wav")}

            # 上传文件
            with open(audio_path, 'rb') as fileobj:
                self.bucket.put_object(object_key, fileobj, headers=headers)
            
            url = self._access_url(object_key)
            logger.info(f"音频上传成功: {object_key}")
            
            return url
            
        except Exception as e:
            logger.error(f"音频上传失败: {e}")
            return None
    
    async def upload_keyframe(self, image_path: str, video_id: str, frame_index: int) -> Optional[str]:
        """
        上传关键帧图片到OSS
        
        Args:
            image_path: 本地图片文件路径
            video_id: 视频唯一标识
            frame_index: 关键帧索引
            
        Returns:
            OSS访问URL或None
        """
        if not self.is_available():
            logger.error("OSS服务不可用")
            return None
        
        try:
            filename = f"frame_{frame_index:03d}.jpg"
            object_key = self._generate_object_key(video_id, "keyframes", filename)
            
            logger.info(f"开始上传关键帧: {image_path} -> {object_key}")
            
            headers = {"Content-Type": self._content_type_for_file(image_path, "image/jpeg")}

            # 上传文件
            with open(image_path, 'rb') as fileobj:
                self.bucket.put_object(object_key, fileobj, headers=headers)
            
            url = self._access_url(object_key)
            logger.debug(f"关键帧上传成功: {object_key}")
            
            return url
            
        except Exception as e:
            logger.error(f"关键帧上传失败: {e}")
            return None
    
    async def upload_metadata(self, metadata: Dict[str, Any], video_id: str) -> Optional[str]:
        """
        上传metadata JSON文件到OSS
        
        Args:
            metadata: 元数据字典
            video_id: 视频唯一标识
            
        Returns:
            OSS访问URL或None
        """
        if not self.is_available():
            logger.error("OSS服务不可用")
            return None
        
        try:
            import json
            
            filename = f"metadata_{video_id}.json"
            object_key = self._generate_object_key(video_id, "metadata", filename)
            
            logger.info(f"开始上传metadata: {object_key}")
            
            # 将metadata转换为JSON字符串
            metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
            
            # 上传JSON内容
            self.bucket.put_object(
                object_key,
                metadata_json.encode('utf-8'),
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            
            url = self._access_url(object_key)
            logger.info(f"Metadata上传成功: {object_key}")
            
            return url
            
        except Exception as e:
            logger.error(f"Metadata上传失败: {e}")
            return None
    
    async def download_file(self, object_key: str, local_path: str) -> bool:
        """
        从OSS下载文件到本地
        
        Args:
            object_key: OSS对象键
            local_path: 本地文件路径
            
        Returns:
            下载是否成功
        """
        if not self.is_available():
            logger.error("OSS服务不可用")
            return False
        
        try:
            logger.info(f"开始下载文件: {object_key} -> {local_path}")
            
            # 确保本地目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 下载文件
            self.bucket.get_object_to_file(object_key, local_path)
            
            logger.info(f"文件下载成功: {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"文件下载失败: {e}")
            return False
    
    def cleanup_video_files(self, video_id: str) -> bool:
        """
        清理指定视频的所有OSS文件
        
        Args:
            video_id: 视频唯一标识
            
        Returns:
            清理是否成功
        """
        if not self.is_available():
            logger.error("OSS服务不可用")
            return False
        
        try:
            # 列出所有相关文件
            prefix = f"videos/"
            objects_to_delete = []
            
            for obj in oss2.ObjectIterator(self.bucket, prefix=prefix):
                if video_id in obj.key:
                    objects_to_delete.append(obj.key)
            
            if objects_to_delete:
                logger.info(f"准备删除{len(objects_to_delete)}个文件")
                
                # 批量删除
                delete_result = self.bucket.batch_delete_objects(objects_to_delete)
                logger.info(f"成功删除{len(delete_result.deleted_keys)}个文件")
                
                if delete_result.delete_errors:
                    logger.warning(f"删除失败的文件: {delete_result.delete_errors}")
            
            return True
            
        except Exception as e:
            logger.error(f"清理OSS文件失败: {e}")
            return False


# 创建单例实例
oss_service = AliyunOSSService()
