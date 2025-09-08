"""
Simplified Video Processing Pipeline
Orchestrates video download, transcription, keyframe extraction, and summarization
"""
import logging
import os
import tempfile
import shutil
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import traceback

from simple_video_service import video_service
from simple_speech_service import get_best_speech_service
from simple_llm_service import llm_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VideoProcessingPipeline:
    """Main pipeline for processing videos from URL to summary"""
    
    def __init__(self):
        """Initialize the processing pipeline"""
        self.video_service = video_service
        self.speech_service = get_best_speech_service()
        self.llm_service = llm_service
        
        # Check service availability
        self.services_status = {
            "video": True,  # Always available
            "speech": self.speech_service is not None and self.speech_service.is_available(),
            "llm": self.llm_service.is_available()
        }
        
        logger.info(f"Pipeline initialized. Services status: {self.services_status}")
    
    def get_services_status(self) -> Dict[str, bool]:
        """Get the status of all services"""
        return self.services_status.copy()
    
    def process_video(self, 
                     video_url: str,
                     language: str = "zh",
                     granularity: str = "medium",
                     num_keyframes: int = 10,
                     keyframe_method: str = "uniform",
                     progress_callback: Optional[Callable[[str, float], None]] = None) -> Dict[str, Any]:
        """
        Process a video from URL to summary
        
        Args:
            video_url: URL of the video to process
            language: Target language for processing ("zh", "en", etc.)
            granularity: Summary granularity ("short", "medium", "detailed")
            num_keyframes: Number of keyframes to extract
            keyframe_method: Method for keyframe extraction ("uniform", "interval", "scene")
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary containing processing results
        """
        def update_progress(stage: str, progress: float):
            """Helper function to update progress"""
            if progress_callback:
                progress_callback(stage, progress)
            logger.info(f"Progress: {stage} - {progress:.1f}%")
        
        session_temp_dir = None
        
        try:
            logger.info(f"Starting video processing pipeline for: {video_url}")
            update_progress("初始化", 0)
            
            # Step 1: Download video and extract audio
            update_progress("下载视频", 10)
            logger.info("Step 1: Downloading video and extracting audio...")
            
            download_result = self.video_service.download_video(
                video_url=video_url,
                extract_audio=True
            )
            
            if download_result["status"] != "success":
                return {
                    "status": "error",
                    "error": f"Video download failed: {download_result.get('error', 'Unknown error')}",
                    "stage": "download"
                }
            
            video_path = download_result.get("video_path")
            audio_path = download_result.get("audio_path")
            metadata = download_result.get("video_metadata", {})
            session_temp_dir = download_result.get("session_temp_dir")
            
            logger.info(f"Download successful - Video: {bool(video_path)}, Audio: {bool(audio_path)}")
            update_progress("下载完成", 25)
            
            # Step 2: Extract keyframes
            keyframes = []
            if video_path:
                update_progress("提取关键帧", 30)
                logger.info("Step 2: Extracting keyframes...")
                
                keyframes = self.video_service.extract_keyframes(
                    video_path=video_path,
                    num_frames=num_keyframes,
                    method=keyframe_method
                )
                
                logger.info(f"Extracted {len(keyframes)} keyframes")
                update_progress("关键帧提取完成", 50)
            else:
                logger.warning("No video file available for keyframe extraction")
            
            # Step 3: Transcribe audio
            transcript = None
            transcription_error = None
            
            if audio_path and self.services_status["speech"]:
                update_progress("音频转录", 55)
                logger.info("Step 3: Transcribing audio...")
                
                try:
                    transcription_result = self.speech_service.transcribe_audio(
                        audio_path=audio_path,
                        language=language
                    )
                    
                    if transcription_result.get("status") == "success":
                        transcript = transcription_result.get("text")
                        logger.info(f"Transcription successful, length: {len(transcript) if transcript else 0}")
                    else:
                        transcription_error = transcription_result.get("error", "Unknown transcription error")
                        logger.warning(f"Transcription failed: {transcription_error}")
                        
                except Exception as e:
                    transcription_error = f"Transcription exception: {str(e)}"
                    logger.exception("Transcription failed with exception")
                
                update_progress("转录完成", 75)
            else:
                if not audio_path:
                    logger.warning("No audio file available for transcription")
                else:
                    logger.warning("Speech service not available")
            
            # Step 4: Generate summary
            summary_text = None
            summary_error = None
            
            if self.services_status["llm"] and (transcript or keyframes):
                update_progress("生成摘要", 80)
                logger.info("Step 4: Generating summary...")
                
                try:
                    # Prepare keyframe paths
                    keyframe_paths = [kf["local_path"] for kf in keyframes] if keyframes else None
                    
                    summary_result = self.llm_service.generate_summary(
                        transcript=transcript,
                        keyframe_paths=keyframe_paths,
                        video_metadata=metadata,
                        language=language,
                        granularity=granularity
                    )
                    
                    if summary_result.get("status") == "success":
                        summary_text = summary_result.get("summary_text")
                        logger.info(f"Summary generation successful, length: {len(summary_text) if summary_text else 0}")
                    else:
                        summary_error = summary_result.get("error", "Unknown summary error")
                        logger.warning(f"Summary generation failed: {summary_error}")
                        
                except Exception as e:
                    summary_error = f"Summary generation exception: {str(e)}"
                    logger.exception("Summary generation failed with exception")
                
                update_progress("摘要生成完成", 95)
            else:
                if not self.services_status["llm"]:
                    summary_error = "LLM service not available"
                    logger.warning("LLM service not available")
                else:
                    summary_error = "No content available for summarization"
                    logger.warning("No transcript or keyframes available for summarization")
            
            # Step 5: Compile results
            update_progress("完成", 100)
            logger.info("Processing pipeline completed")
            
            # Determine overall status
            overall_status = "success"
            errors = []
            
            if download_result["status"] != "success":
                overall_status = "error"
                errors.append(f"Download: {download_result.get('error')}")
            
            if transcription_error:
                errors.append(f"Transcription: {transcription_error}")
            
            if summary_error:
                errors.append(f"Summary: {summary_error}")
            
            # If we have at least some results, consider it partial success
            if summary_text or transcript or keyframes:
                if errors:
                    overall_status = "partial_success"
            elif errors:
                overall_status = "error"
            
            result = {
                "status": overall_status,
                "video_metadata": metadata,
                "transcript": transcript,
                "summary": summary_text,
                "keyframes_count": len(keyframes),
                "keyframes": keyframes,
                "errors": errors,
                "services_used": {
                    "video": True,
                    "speech": self.services_status["speech"] and bool(transcript),
                    "llm": self.services_status["llm"] and bool(summary_text)
                }
            }
            
            return result
            
        except Exception as e:
            error_msg = f"Pipeline processing failed: {str(e)}"
            logger.exception(error_msg)
            update_progress("错误", 0)
            
            return {
                "status": "error",
                "error": error_msg,
                "stage": "pipeline",
                "traceback": traceback.format_exc()
            }
        
        finally:
            # Cleanup temporary files
            if session_temp_dir:
                try:
                    self.video_service.cleanup_session(session_temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup session directory: {e}")
    
    def get_processing_info(self) -> Dict[str, Any]:
        """Get information about the processing pipeline and available services"""
        return {
            "services_status": self.services_status,
            "video_service": {
                "available": True,
                "description": "Video download and keyframe extraction using yt-dlp"
            },
            "speech_service": {
                "available": self.services_status["speech"],
                "description": "Audio transcription using OpenAI Whisper API or local speech recognition",
                "service_type": type(self.speech_service).__name__ if self.speech_service else None
            },
            "llm_service": {
                "available": self.services_status["llm"],
                "description": "Video summarization using OpenAI GPT-4 Vision or Qwen VL",
                "primary_service": getattr(self.llm_service, 'primary_service', None)
            }
        }


# Create singleton instance
processing_pipeline = VideoProcessingPipeline()