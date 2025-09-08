"""
Simplified Video Service
Handles video download and keyframe extraction without database dependencies
"""
import logging
import uuid
import os
import subprocess
import json
import tempfile
import shutil
from datetime import datetime
from typing import Dict, List, Any, Optional
import pathlib
import cv2
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common download options for yt-dlp
COMMON_OPTS = {
    'noplaylist': True,
    'retries': 10,
    'fragment_retries': 10,
    'socket_timeout': 60,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': False,
    'no_warnings': False,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Sec-Fetch-Mode': 'navigate',
    }
}


class SimpleVideoService:
    """Simplified video processing service"""
    
    def __init__(self, temp_dir: str = None):
        """Initialize the video service with optional temporary directory"""
        if temp_dir:
            self.temp_dir = pathlib.Path(temp_dir)
        else:
            self.temp_dir = pathlib.Path(tempfile.gettempdir()) / "simple_video_service"
        
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized SimpleVideoService with temp dir: {self.temp_dir}")
    
    def _extract_video_id(self, video_url: str) -> str:
        """Extract video ID from YouTube URL or generate hash-based ID"""
        try:
            if "youtu.be/" in video_url:
                return video_url.split("youtu.be/")[-1].split("?")[0]
            elif "youtube.com/watch" in video_url:
                return video_url.split("v=")[-1].split("&")[0]
            else:
                # For non-YouTube links, generate hash-based ID
                return str(abs(hash(video_url)) % (10**8))
        except Exception:
            return str(uuid.uuid4())
    
    def download_video(self, video_url: str, extract_audio: bool = True) -> Dict[str, Any]:
        """
        Download video and optionally extract audio using yt-dlp
        
        Args:
            video_url: URL of the video to download
            extract_audio: Whether to extract audio
            
        Returns:
            Dictionary containing download results
        """
        session_id = str(uuid.uuid4())[:8]
        session_temp_dir = self.temp_dir / f"session_{session_id}"
        session_temp_dir.mkdir(exist_ok=True)
        
        try:
            logger.info(f"Starting video processing for URL: {video_url}")
            
            # Generate unique filename
            base_id = self._extract_video_id(video_url)
            unique_filename_base = session_temp_dir / f"{base_id}_{session_id}"
            video_output_template = f"{unique_filename_base}_video.%(ext)s"
            audio_output_template = f"{unique_filename_base}_audio.%(ext)s"
            
            # Extract metadata
            metadata_cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-warnings',
                '--ignore-errors',
                video_url
            ]
            
            logger.info("Extracting video metadata...")
            metadata_process = subprocess.run(metadata_cmd, capture_output=True, text=True, check=False)
            
            metadata = {}
            if metadata_process.returncode == 0 and metadata_process.stdout:
                try:
                    metadata = json.loads(metadata_process.stdout)
                    logger.info(f"Successfully extracted metadata: {metadata.get('title', 'N/A')}")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse yt-dlp metadata JSON")
            
            # Download video
            video_cmd = [
                'yt-dlp',
                '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                '--merge-output-format', 'mp4',
                '-o', video_output_template,
                '--no-warnings',
                '--ignore-errors',
                video_url
            ]
            
            logger.info("Downloading video...")
            video_process = subprocess.run(video_cmd, capture_output=True, text=True, check=False)
            
            video_path = None
            if video_process.returncode == 0:
                potential_video_path = str(unique_filename_base) + "_video.mp4"
                if os.path.exists(potential_video_path):
                    video_path = potential_video_path
                    logger.info(f"Video download successful: {video_path}")
                else:
                    # Try to find any video file with the pattern
                    for f in session_temp_dir.iterdir():
                        if f.name.startswith(f"{base_id}_{session_id}_video"):
                            video_path = str(f)
                            logger.info(f"Found video file: {video_path}")
                            break
            
            # Extract audio if requested
            audio_path = None
            if extract_audio:
                audio_cmd = [
                    'yt-dlp',
                    '-x',
                    '--audio-format', 'mp3',
                    '--audio-quality', '0',
                    '-o', audio_output_template,
                    '--no-warnings',
                    '--ignore-errors',
                    video_url
                ]
                
                logger.info("Extracting audio...")
                audio_process = subprocess.run(audio_cmd, capture_output=True, text=True, check=False)
                
                potential_audio_path = str(unique_filename_base) + "_audio.mp3"
                if os.path.exists(potential_audio_path):
                    audio_path = potential_audio_path
                    logger.info(f"Audio extraction successful: {audio_path}")
            
            # Clean metadata
            cleaned_metadata = {
                "title": metadata.get("title"),
                "uploader": metadata.get("uploader"),
                "upload_date": metadata.get("upload_date"),
                "duration": metadata.get("duration"),
                "duration_string": metadata.get("duration_string"),
                "description": metadata.get("description"),
                "thumbnail": metadata.get("thumbnail"),
                "view_count": metadata.get("view_count"),
                "like_count": metadata.get("like_count"),
                "channel_url": metadata.get("channel_url"),
                "original_url": metadata.get("original_url", video_url),
                "webpage_url": metadata.get("webpage_url", video_url)
            }
            
            if video_path or audio_path:
                return {
                    "status": "success",
                    "video_path": video_path,
                    "audio_path": audio_path,
                    "video_metadata": cleaned_metadata,
                    "session_temp_dir": str(session_temp_dir),
                    "session_id": session_id
                }
            else:
                error_msg = "Both video download and audio extraction failed"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg,
                    "video_path": None,
                    "audio_path": None,
                    "video_metadata": {},
                    "session_temp_dir": str(session_temp_dir),
                    "session_id": session_id
                }
                
        except Exception as e:
            error_msg = f"Unexpected error during video processing: {str(e)}"
            logger.exception(error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "video_path": None,
                "audio_path": None,
                "video_metadata": {},
                "session_temp_dir": str(session_temp_dir) if 'session_temp_dir' in locals() else None,
                "session_id": session_id if 'session_id' in locals() else None
            }
    
    def extract_keyframes(self, video_path: str, num_frames: int = 10, method: str = "uniform") -> List[Dict[str, Any]]:
        """
        Extract keyframes from video
        
        Args:
            video_path: Path to the video file
            num_frames: Number of frames to extract
            method: Extraction method ("uniform", "interval", "scene")
            
        Returns:
            List of dictionaries containing frame information
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return []
        
        try:
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"Video info: {total_frames} frames, {fps:.2f} fps, {duration:.2f}s duration")
            
            keyframes = []
            output_dir = pathlib.Path(video_path).parent / "keyframes"
            output_dir.mkdir(exist_ok=True)
            
            if method == "uniform":
                # Extract frames at uniform intervals
                frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
            elif method == "interval":
                # Extract frames at fixed time intervals
                interval = duration / num_frames
                frame_indices = [int(i * interval * fps) for i in range(num_frames)]
            else:  # scene detection or fallback to uniform
                # For simplicity, fallback to uniform method
                frame_indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
            
            for i, frame_idx in enumerate(frame_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if ret:
                    timestamp = frame_idx / fps if fps > 0 else 0
                    frame_filename = f"frame_{i:03d}_{timestamp:.2f}s.jpg"
                    frame_path = output_dir / frame_filename
                    
                    # Save frame
                    cv2.imwrite(str(frame_path), frame)
                    
                    keyframes.append({
                        "frame_index": frame_idx,
                        "timestamp": timestamp,
                        "local_path": str(frame_path),
                        "filename": frame_filename
                    })
                    
                    logger.debug(f"Extracted frame {i+1}/{num_frames} at {timestamp:.2f}s")
            
            cap.release()
            logger.info(f"Successfully extracted {len(keyframes)} keyframes")
            return keyframes
            
        except Exception as e:
            logger.error(f"Error extracting keyframes: {str(e)}")
            return []
    
    def cleanup_session(self, session_temp_dir: str):
        """Clean up temporary session directory"""
        if session_temp_dir and os.path.exists(session_temp_dir):
            try:
                shutil.rmtree(session_temp_dir)
                logger.info(f"Cleaned up session directory: {session_temp_dir}")
            except Exception as e:
                logger.error(f"Failed to clean up session directory {session_temp_dir}: {e}")


# Create singleton instance
video_service = SimpleVideoService()