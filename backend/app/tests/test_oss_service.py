"""
Unit tests for the OSS service.
"""
import pytest
import os
from unittest.mock import patch, MagicMock

from ..services.oss_service import AliyunOSSService


def test_generate_object_key():
    """Test generating OSS object keys."""
    with patch.dict(os.environ, {
        "ALIYUN_ACCESS_KEY_ID": "test-key",
        "ALIYUN_ACCESS_KEY_SECRET": "test-secret",
        "ALIYUN_OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com",
        "ALIYUN_OSS_BUCKET": "test-bucket"
    }):
        service = AliyunOSSService()
        
        # 测试生成对象键
        object_key = service._generate_object_key("test-video-id", "original", "test.mp4")
        
        # 验证对象键格式
        assert "videos/" in object_key
        assert "test-video-id" in object_key
        assert "original" in object_key
        assert "test.mp4" in object_key


def test_service_availability():
    """Test service availability with complete configuration."""
    with patch.dict(os.environ, {
        "ALIYUN_ACCESS_KEY_ID": "test-key",
        "ALIYUN_ACCESS_KEY_SECRET": "test-secret",
        "ALIYUN_OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com",
        "ALIYUN_OSS_BUCKET": "test-bucket"
    }):
        service = AliyunOSSService()
        assert service.is_available() == True


def test_service_unavailability():
    """Test service unavailability with incomplete configuration."""
    with patch.dict(os.environ, {}, clear=True):
        service = AliyunOSSService()
        assert service.is_available() == False


if __name__ == "__main__":
    pytest.main([__file__])