"""
Unit tests for the OSS service.
"""
import pytest
import os
from unittest.mock import patch, MagicMock

from ..services.oss_service import AliyunOSSService
from ..core.config import settings


def test_generate_object_key():
    """Test generating OSS object keys."""
    # Mock settings directly
    with patch.object(settings, 'ALIYUN_ACCESS_KEY_ID', 'test-key'), \
         patch.object(settings, 'ALIYUN_ACCESS_KEY_SECRET', 'test-secret'), \
         patch.object(settings, 'ALIYUN_OSS_ENDPOINT', 'https://oss-cn-hangzhou.aliyuncs.com'), \
         patch.object(settings, 'ALIYUN_OSS_BUCKET', 'test-bucket'):
        
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
    # Mock settings directly
    with patch.object(settings, 'ALIYUN_ACCESS_KEY_ID', 'test-key'), \
         patch.object(settings, 'ALIYUN_ACCESS_KEY_SECRET', 'test-secret'), \
         patch.object(settings, 'ALIYUN_OSS_ENDPOINT', 'https://oss-cn-hangzhou.aliyuncs.com'), \
         patch.object(settings, 'ALIYUN_OSS_BUCKET', 'test-bucket'):
        
        service = AliyunOSSService()
        assert service.is_available() == True


def test_service_unavailability():
    """Test service unavailability with incomplete configuration."""
    # Mock settings with empty values
    with patch.object(settings, 'ALIYUN_ACCESS_KEY_ID', ''), \
         patch.object(settings, 'ALIYUN_ACCESS_KEY_SECRET', ''), \
         patch.object(settings, 'ALIYUN_OSS_ENDPOINT', ''), \
         patch.object(settings, 'ALIYUN_OSS_BUCKET', ''):
        
        service = AliyunOSSService()
        assert service.is_available() == False


if __name__ == "__main__":
    pytest.main([__file__])