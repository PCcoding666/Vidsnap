"""
Unit tests for the video service.
"""
import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock

from ..services.video_service import AliyunVideoService


@pytest.fixture
def video_service():
    """Create a video service instance for testing."""
    return AliyunVideoService()


def test_generate_video_id(video_service):
    """Test video ID generation."""
    video_id1 = video_service._generate_video_id()
    video_id2 = video_service._generate_video_id()
    
    assert isinstance(video_id1, str)
    assert len(video_id1) > 0
    assert video_id1 != video_id2


def test_extract_video_id_from_url(video_service):
    """Test extracting video ID from YouTube URL."""
    # 测试youtu.be格式
    url1 = "https://youtu.be/dQw4w9WgXcQ"
    video_id1 = video_service._extract_video_id_from_url(url1)
    assert video_id1 == "dQw4w9WgXcQ"
    
    # 测试youtube.com/watch格式
    url2 = "https://www.youtube.com/watch?v=ScMzIvxBSi4"
    video_id2 = video_service._extract_video_id_from_url(url2)
    assert video_id2 == "ScMzIvxBSi4"
    
    # 测试其他URL格式
    url3 = "https://example.com/video"
    video_id3 = video_service._extract_video_id_from_url(url3)
    assert isinstance(video_id3, str)
    assert len(video_id3) > 0


@pytest.mark.asyncio
async def test_uniform_sampling(video_service):
    """Test uniform sampling fallback."""
    # 使用一个简单的测试，因为我们没有实际的视频文件
    with patch.object(video_service, '_extract_video_metadata', return_value={'duration': 60.0}):
        timestamps = await video_service._uniform_sampling("fake_video.mp4", 5)
        
        assert len(timestamps) == 5
        assert timestamps[0] > 0
        assert timestamps[-1] < 60.0


def test_parse_scene_timestamps(video_service):
    """Test parsing scene timestamps from ffmpeg output."""
    # 模拟ffmpeg输出
    stderr_output = """
    pts_time:1.23
    pts_time:5.67
    pts_time:10.45
    pts_time:5.67  # 重复的时间戳
    """
    
    timestamps = video_service._parse_scene_timestamps(stderr_output)
    
    # 应该去重并排序
    assert len(timestamps) == 3
    assert timestamps == [1.23, 5.67, 10.45]


if __name__ == "__main__":
    pytest.main([__file__])