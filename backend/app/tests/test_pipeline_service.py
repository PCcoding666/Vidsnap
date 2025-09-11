"""
Unit tests for the pipeline service.
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime

from ..services.pipeline_service import AliyunVideoProcessingPipeline
from ..models.video import VideoInfo
from ..models.analysis import TranscriptSegment, TranscriptMetadata, KeyframeMetadata


@pytest.fixture
def pipeline_service():
    """Create a pipeline service instance for testing."""
    with patch.dict(os.environ, {
        "ALIYUN_ACCESS_KEY_ID": "test-key",
        "ALIYUN_ACCESS_KEY_SECRET": "test-secret",
        "ALIYUN_OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com",
        "ALIYUN_OSS_BUCKET": "test-bucket",
        "OPENAI_API_KEY": "test-openai-key"
    }):
        return AliyunVideoProcessingPipeline()


def test_create_empty_transcript(pipeline_service):
    """Test creating empty transcript."""
    empty_transcript = pipeline_service._create_empty_transcript()
    
    assert hasattr(empty_transcript, 'segments')
    assert hasattr(empty_transcript, 'language')
    assert hasattr(empty_transcript, 'confidence')
    assert hasattr(empty_transcript, 'audio_oss_url')
    
    assert empty_transcript.segments == []
    assert empty_transcript.language == "zh-CN"
    assert empty_transcript.confidence == 0.0
    assert empty_transcript.audio_oss_url == ""


def test_check_services_availability(pipeline_service):
    """Test checking service availability."""
    # 由于我们mock了环境变量，所有服务都应该可用
    availability = pipeline_service.check_services_availability()
    
    assert isinstance(availability, dict)
    assert "video_service" in availability
    assert "speech_service" in availability
    assert "oss_service" in availability
    
    # 视频服务总是可用
    assert availability["video_service"] == True
    
    # 其他服务应该根据配置可用
    assert availability["speech_service"] == True
    assert availability["oss_service"] == True


def test_generate_unified_metadata(pipeline_service):
    """Test generating unified metadata."""
    # 创建测试数据
    video_info = VideoInfo(
        video_id="test-video-id",
        title="Test Video",
        duration=120.0,
        oss_video_url="http://example.com/video.mp4",
        upload_time=datetime.now(),
        source_type="youtube",
        original_url="https://youtube.com/watch?v=test"
    )
    
    keyframes = [
        KeyframeMetadata(
            frame_id=1,
            timestamp=10.0,
            oss_image_url="http://example.com/frame1.jpg",
            scene_description="Scene 1"
        )
    ]
    
    transcript_segments = [
        TranscriptSegment(
            text="This is a test transcript",
            start_time=0.0,
            end_time=5.0,
            confidence=0.9
        )
    ]
    
    transcript_result = MagicMock()
    transcript_result.segments = transcript_segments
    transcript_result.language = "en"
    transcript_result.confidence = 0.9
    transcript_result.audio_oss_url = "http://example.com/audio.mp3"
    
    video_metadata = {
        "format_name": "mp4",
        "size": 1024000,
        "width": 1920,
        "height": 1080
    }
    
    # 调用方法
    metadata = asyncio.run(pipeline_service._generate_unified_metadata(
        video_info, keyframes, transcript_result, video_metadata
    ))
    
    # 验证结果
    assert metadata.video_id == "test-video-id"
    assert metadata.title == "Test Video"
    assert metadata.duration == 120.0
    assert metadata.oss_video_url == "http://example.com/video.mp4"
    assert metadata.source_type == "youtube"
    assert metadata.original_url == "https://youtube.com/watch?v=test"
    
    # 验证关键帧
    assert len(metadata.keyframes) == 1
    assert metadata.keyframes[0].frame_id == 1
    assert metadata.keyframes[0].timestamp == 10.0
    assert metadata.keyframes[0].oss_image_url == "http://example.com/frame1.jpg"
    assert metadata.keyframes[0].scene_description == "Scene 1"
    
    # 验证转录
    assert metadata.transcript.language == "en"
    assert metadata.transcript.overall_confidence == 0.9
    assert metadata.transcript.oss_audio_url == "http://example.com/audio.mp3"
    assert len(metadata.transcript.segments) == 1
    assert metadata.transcript.segments[0].text == "This is a test transcript"
    
    # 验证技术信息
    assert metadata.video_format == "mp4"
    assert metadata.video_size == 1024000
    assert metadata.video_resolution == "1920x1080"


if __name__ == "__main__":
    pytest.main([__file__])