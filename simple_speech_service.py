"""
Simplified Speech Transcription Service
Handles audio transcription using OpenAI Whisper API
"""
import logging
import os
import tempfile
from typing import Dict, Any, Optional
from pathlib import Path
import requests
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleSpeechService:
    """Simplified speech transcription service using OpenAI Whisper API"""
    
    def __init__(self):
        """Initialize the speech service"""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = "https://api.openai.com/v1"
        
        if not self.api_key:
            logger.warning("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
            self.available = False
        else:
            self.available = True
            logger.info("SimpleSpeechService initialized successfully")
    
    def is_available(self) -> bool:
        """Check if the speech service is available"""
        return self.available and bool(self.api_key)
    
    def transcribe_audio(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """
        Transcribe audio file using OpenAI Whisper API
        
        Args:
            audio_path: Path to the audio file
            language: Language code (e.g., "en", "zh", "auto" for auto-detection)
            
        Returns:
            Dictionary containing transcription results
        """
        if not self.is_available():
            return {
                "status": "error",
                "error": "Speech service is not available. Please check OpenAI API key.",
                "text": None
            }
        
        if not os.path.exists(audio_path):
            return {
                "status": "error",
                "error": f"Audio file not found: {audio_path}",
                "text": None
            }
        
        try:
            logger.info(f"Starting transcription for: {audio_path}")
            
            # Prepare the API request
            url = f"{self.api_base}/audio/transcriptions"
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Prepare files and data
            with open(audio_path, "rb") as audio_file:
                files = {
                    "file": (os.path.basename(audio_path), audio_file, "audio/mpeg")
                }
                
                data = {
                    "model": "whisper-1",
                    "response_format": "json"
                }
                
                # Add language if specified and not auto
                if language and language != "auto":
                    # Map common language codes
                    language_map = {
                        "zh": "zh",
                        "en": "en",
                        "es": "es",
                        "fr": "fr",
                        "de": "de",
                        "it": "it",
                        "pt": "pt",
                        "ru": "ru",
                        "ja": "ja",
                        "ko": "ko"
                    }
                    
                    if language in language_map:
                        data["language"] = language_map[language]
                
                logger.info("Sending transcription request to OpenAI...")
                response = requests.post(url, headers=headers, files=files, data=data, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                transcription_text = result.get("text", "")
                
                logger.info(f"Transcription successful. Text length: {len(transcription_text)}")
                logger.debug(f"Transcription preview: {transcription_text[:200]}...")
                
                return {
                    "status": "success",
                    "text": transcription_text,
                    "language": result.get("language"),
                    "error": None
                }
            else:
                error_msg = f"OpenAI API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg,
                    "text": None
                }
                
        except requests.exceptions.Timeout:
            error_msg = "Transcription request timed out"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "text": None
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error during transcription: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "text": None
            }
        except Exception as e:
            error_msg = f"Unexpected error during transcription: {str(e)}"
            logger.exception(error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "text": None
            }


# Alternative simple local transcription using speech_recognition library (fallback)
class LocalSpeechService:
    """Local speech transcription service using speech_recognition library"""
    
    def __init__(self):
        """Initialize local speech service"""
        try:
            import speech_recognition as sr
            self.sr = sr
            self.recognizer = sr.Recognizer()
            self.available = True
            logger.info("LocalSpeechService initialized successfully")
        except ImportError:
            logger.warning("speech_recognition library not available")
            self.available = False
            self.sr = None
            self.recognizer = None
    
    def is_available(self) -> bool:
        """Check if local speech service is available"""
        return self.available
    
    def transcribe_audio(self, audio_path: str, language: str = "auto") -> Dict[str, Any]:
        """
        Transcribe audio using local speech recognition
        
        Args:
            audio_path: Path to the audio file
            language: Language code
            
        Returns:
            Dictionary containing transcription results
        """
        if not self.is_available():
            return {
                "status": "error",
                "error": "Local speech recognition is not available",
                "text": None
            }
        
        try:
            # Convert audio to WAV format if needed
            audio_file = self.sr.AudioFile(audio_path)
            with audio_file as source:
                audio_data = self.recognizer.record(source)
            
            # Map language codes
            language_map = {
                "zh": "zh-CN",
                "en": "en-US",
                "auto": "en-US"  # Default to English
            }
            
            lang_code = language_map.get(language, "en-US")
            
            # Use Google Speech Recognition (free tier)
            text = self.recognizer.recognize_google(audio_data, language=lang_code)
            
            return {
                "status": "success",
                "text": text,
                "language": language,
                "error": None
            }
            
        except Exception as e:
            error_msg = f"Local transcription error: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "text": None
            }


# Create singleton instances
speech_service = SimpleSpeechService()
local_speech_service = LocalSpeechService()


def get_best_speech_service() -> Any:
    """Get the best available speech service"""
    if speech_service.is_available():
        return speech_service
    elif local_speech_service.is_available():
        logger.info("Using local speech service as fallback")
        return local_speech_service
    else:
        logger.warning("No speech service available")
        return None