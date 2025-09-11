"""
Unit tests for the speech service.
"""
import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock

from ..services.speech_service import OpenAISpeechService, TranscriptionResult


@pytest.fixture
def speech_service():
    """Create a speech service instance for testing."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        return OpenAISpeechService()


def test_service_initialization():
    """Test service initialization with API key."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        service = OpenAISpeechService()
        assert service.is_available() == True


def test_service_initialization_without_key():
    """Test service initialization without API key."""
    with patch.dict(os.environ, {}, clear=True):
        service = OpenAISpeechService()
        assert service.is_available() == False


def test_parse_transcription_to_segments():
    """Test parsing transcription data to segments."""
    service = OpenAISpeechService()
    
    # 模拟OpenAI转录数据
    transcription_data = {
        "language": "zh",
        "text": "这是测试文本",
        "segments": [
            {
                "text": "这是第一段",
                "start": 0.0,
                "end": 0.5,
                "avg_logprob": -0.7
            },
            {
                "text": "这是第二段",
                "start": 0.5,
                "end": 1.0,
                "avg_logprob": -0.3
            }
        ]
    }
    
    result = service._parse_transcription_to_segments(transcription_data, "http://example.com/audio.mp3")
    
    assert isinstance(result, TranscriptionResult)
    assert result.language == "zh"
    assert len(result.segments) == 2
    assert result.audio_oss_url == "http://example.com/audio.mp3"
    
    # 检查第一个段落
    segment1 = result.segments[0]
    assert segment1.text == "这是第一段"
    assert segment1.start_time == 0.0
    assert segment1.end_time == 0.5
    assert segment1.confidence > 0 and segment1.confidence < 1
    
    # 检查第二个段落
    segment2 = result.segments[1]
    assert segment2.text == "这是第二段"
    assert segment2.start_time == 0.5
    assert segment2.end_time == 1.0
    assert segment2.confidence > 0 and segment2.confidence < 1


def test_parse_transcription_without_segments():
    """Test parsing transcription data without segments."""
    service = OpenAISpeechService()
    
    # 模拟没有段落的OpenAI转录数据
    transcription_data = {
        "language": "zh",
        "text": "这是测试文本",
        "segments": []
    }
    
    result = service._parse_transcription_to_segments(transcription_data, "http://example.com/audio.mp3")
    
    assert isinstance(result, TranscriptionResult)
    assert result.language == "zh"
    assert len(result.segments) == 1  # 应该创建一个包含全文的段落
    assert result.segments[0].text == "这是测试文本"
    assert result.audio_oss_url == "http://example.com/audio.mp3"


if __name__ == "__main__":
    pytest.main([__file__])