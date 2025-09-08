"""
Simplified LLM Summary Service
Handles video summarization using LLM APIs (OpenAI/Qwen)
"""
import logging
import os
import base64
import requests
from typing import Dict, List, Any, Optional
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleLLMService:
    """Simplified LLM service for video summarization"""
    
    def __init__(self):
        """Initialize the LLM service"""
        # Try OpenAI first, then Qwen as fallback
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.qwen_api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        
        self.openai_available = bool(self.openai_api_key)
        self.qwen_available = bool(self.qwen_api_key)
        
        if self.openai_available:
            self.primary_service = "openai"
            logger.info("Using OpenAI as primary LLM service")
        elif self.qwen_available:
            self.primary_service = "qwen"
            logger.info("Using Qwen as primary LLM service")
        else:
            self.primary_service = None
            logger.warning("No LLM API key found. Set OPENAI_API_KEY or QWEN_API_KEY/DASHSCOPE_API_KEY")
        
        # API endpoints
        self.openai_api_base = "https://api.openai.com/v1"
        self.qwen_api_base = "https://dashscope.aliyuncs.com/api/v1"
    
    def is_available(self) -> bool:
        """Check if any LLM service is available"""
        return self.openai_available or self.qwen_available
    
    def encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encode image file to base64 string"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image {image_path}: {e}")
            return None
    
    def generate_summary_openai(self, 
                               transcript: Optional[str] = None,
                               keyframe_paths: Optional[List[str]] = None,
                               video_metadata: Optional[Dict] = None,
                               language: str = "zh",
                               granularity: str = "medium") -> Dict[str, Any]:
        """Generate summary using OpenAI GPT-4 Vision"""
        if not self.openai_available:
            return {"status": "error", "error": "OpenAI API not available"}
        
        try:
            # Build system prompt
            system_prompts = {
                "en": {
                    "short": "You are a professional video analyst. Generate a concise summary of no more than 200 words.",
                    "medium": "You are a professional video analyst. Provide a summary that includes main content, key points, and conclusions.",
                    "detailed": "You are a professional video analyst. Describe the video content in detail."
                },
                "zh": {
                    "short": "你是一位专业的视频分析师。请生成不超过200字的简洁摘要。",
                    "medium": "你是一位专业的视频分析师。请提供包含主要内容、关键点和结论的摘要。",
                    "detailed": "你是一位专业的视频分析师。请详细描述视频内容。"
                }
            }
            
            system_prompt = system_prompts.get(language, system_prompts["zh"]).get(granularity, system_prompts[language]["medium"])
            
            # Build user content
            user_content = []
            
            # Add metadata if available
            if video_metadata:
                metadata_text = f"视频信息:\n标题: {video_metadata.get('title', 'N/A')}\n"
                if video_metadata.get('description'):
                    metadata_text += f"描述: {video_metadata.get('description', '')[:300]}...\n"
                user_content.append({"type": "text", "text": metadata_text})
            
            # Add transcript if available
            if transcript:
                transcript_text = f"音频转录:\n{transcript[:3000]}..."  # Limit length
                user_content.append({"type": "text", "text": transcript_text})
            
            # Add keyframes if available
            if keyframe_paths:
                user_content.append({"type": "text", "text": "以下是视频关键帧:"})
                for i, image_path in enumerate(keyframe_paths[:10]):  # Limit to 10 images
                    base64_image = self.encode_image_to_base64(image_path)
                    if base64_image:
                        user_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        })
            
            if not user_content:
                return {"status": "error", "error": "No content provided for summarization"}
            
            user_content.append({"type": "text", "text": "请基于以上信息生成视频摘要。"})
            
            # Make API request
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-4-vision-preview",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": 1000
            }
            
            logger.info("Sending request to OpenAI GPT-4 Vision...")
            response = requests.post(
                f"{self.openai_api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                summary_text = result["choices"][0]["message"]["content"]
                
                logger.info(f"OpenAI summarization successful. Summary length: {len(summary_text)}")
                
                return {
                    "status": "success",
                    "summary_text": summary_text,
                    "service_used": "openai",
                    "error": None
                }
            else:
                error_msg = f"OpenAI API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {"status": "error", "error": error_msg}
                
        except Exception as e:
            error_msg = f"OpenAI summarization error: {str(e)}"
            logger.exception(error_msg)
            return {"status": "error", "error": error_msg}
    
    def generate_summary_qwen(self, 
                             transcript: Optional[str] = None,
                             keyframe_paths: Optional[List[str]] = None,
                             video_metadata: Optional[Dict] = None,
                             language: str = "zh",
                             granularity: str = "medium") -> Dict[str, Any]:
        """Generate summary using Qwen VL"""
        if not self.qwen_available:
            return {"status": "error", "error": "Qwen API not available"}
        
        try:
            # Build system prompt
            system_prompts = {
                "en": {
                    "short": "You are a professional video analyst. Generate a concise summary of no more than 200 words.",
                    "medium": "You are a professional video analyst. Provide a summary that includes main content, key points, and conclusions.",
                    "detailed": "You are a professional video analyst. Describe the video content in detail."
                },
                "zh": {
                    "short": "你是一位专业的视频分析师。请生成不超过200字的简洁摘要。",
                    "medium": "你是一位专业的视频分析师。请提供包含主要内容、关键点和结论的摘要。",
                    "detailed": "你是一位专业的视频分析师。请详细描述视频内容。"
                }
            }
            
            system_prompt = system_prompts.get(language, system_prompts["zh"]).get(granularity, system_prompts[language]["medium"])
            
            # Build user content
            user_content = []
            
            # Add metadata if available
            if video_metadata:
                metadata_text = f"视频信息:\n标题: {video_metadata.get('title', 'N/A')}\n"
                if video_metadata.get('description'):
                    metadata_text += f"描述: {video_metadata.get('description', '')[:300]}...\n"
                user_content.append({"type": "text", "text": metadata_text})
            
            # Add transcript if available
            if transcript:
                transcript_text = f"音频转录:\n{transcript[:3000]}..."  # Limit length
                user_content.append({"type": "text", "text": transcript_text})
            
            # Add keyframes if available
            if keyframe_paths:
                user_content.append({"type": "text", "text": "以下是视频关键帧:"})
                for i, image_path in enumerate(keyframe_paths[:8]):  # Limit to 8 images for Qwen
                    # For Qwen, we can use local file paths directly
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"file://{image_path}"
                        }
                    })
            
            if not user_content:
                return {"status": "error", "error": "No content provided for summarization"}
            
            user_content.append({"type": "text", "text": "请基于以上信息生成视频摘要。"})
            
            # Make API request
            headers = {
                "Authorization": f"Bearer {self.qwen_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "qwen-vl-max",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            }
            
            logger.info("Sending request to Qwen VL...")
            response = requests.post(
                f"{self.qwen_api_base}/services/aigc/multimodal-generation/generation",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                summary_text = result["output"]["choices"][0]["message"]["content"]
                
                logger.info(f"Qwen summarization successful. Summary length: {len(summary_text)}")
                
                return {
                    "status": "success",
                    "summary_text": summary_text,
                    "service_used": "qwen",
                    "error": None
                }
            else:
                error_msg = f"Qwen API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {"status": "error", "error": error_msg}
                
        except Exception as e:
            error_msg = f"Qwen summarization error: {str(e)}"
            logger.exception(error_msg)
            return {"status": "error", "error": error_msg}
    
    def generate_summary(self, 
                        transcript: Optional[str] = None,
                        keyframe_paths: Optional[List[str]] = None,
                        video_metadata: Optional[Dict] = None,
                        language: str = "zh",
                        granularity: str = "medium") -> Dict[str, Any]:
        """
        Generate summary using the best available LLM service
        
        Args:
            transcript: Audio transcription text
            keyframe_paths: List of local paths to keyframe images
            video_metadata: Video metadata dictionary
            language: Target language for summary
            granularity: Summary granularity ("short", "medium", "detailed")
            
        Returns:
            Dictionary containing summary results
        """
        if not self.is_available():
            return {"status": "error", "error": "No LLM service available"}
        
        # Try primary service first
        if self.primary_service == "openai":
            result = self.generate_summary_openai(transcript, keyframe_paths, video_metadata, language, granularity)
            if result.get("status") == "success":
                return result
            
            # Fallback to Qwen if available
            if self.qwen_available:
                logger.info("OpenAI failed, trying Qwen as fallback...")
                return self.generate_summary_qwen(transcript, keyframe_paths, video_metadata, language, granularity)
        
        elif self.primary_service == "qwen":
            result = self.generate_summary_qwen(transcript, keyframe_paths, video_metadata, language, granularity)
            if result.get("status") == "success":
                return result
            
            # Fallback to OpenAI if available
            if self.openai_available:
                logger.info("Qwen failed, trying OpenAI as fallback...")
                return self.generate_summary_openai(transcript, keyframe_paths, video_metadata, language, granularity)
        
        return {"status": "error", "error": "All LLM services failed"}


# Create singleton instance
llm_service = SimpleLLMService()