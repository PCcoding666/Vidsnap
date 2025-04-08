import os
import logging
import requests
import base64
import uuid
from typing import Optional, List, Dict, Any, Tuple, Union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_504_GATEWAY_TIMEOUT
import time
from starlette.requests import ClientDisconnect
import datetime
import json
import pprint
import traceback

from app.core.config import settings
from app.services.summary.qwen_service_part1 import QwenService as QwenServiceBase
from app.services.summary.utils import log_api_request, log_api_response, log_api_error

# 确保环境变量在服务实例化时已加载
load_dotenv(verbose=True)

# 配置日志
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
# 添加文件处理器，确保日志同时写入文件
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

# 添加文件处理器以记录到文件
file_handler = logging.FileHandler('qwen_api_debug.log')
file_handler.setLevel(log_level)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info("====== 千问服务开始初始化 ======")
logger.info(f"qwen_service_part2模块: QWEN_API_KEY 存在: {'是' if os.getenv('QWEN_API_KEY') else '否'}")
logger.info(f"qwen_service_part2模块: QWEN_API_BASE: {os.getenv('QWEN_API_BASE', '未设置')}")
logger.info(f"qwen_service_part2模块: QWEN_MODEL: {os.getenv('QWEN_MODEL', '未设置')}")
logger.info(f"qwen_service_part2模块: 当前工作目录: {os.getcwd()}")
logger.info(f"日志级别: {logging.getLevelName(logger.level)}")

app = FastAPI()
REQUEST_TIMEOUT = 120.0  # 设置120秒超时

@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        start_time = time.time()
        result = await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
        logger.info(f"操作完成，耗时: {time.time() - start_time:.2f}秒")
        return result
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": "请求处理超时"}
        )

class QwenService(QwenServiceBase):
    """千问API服务扩展类，实现场景检测和摘要生成功能"""
    
    def __init__(self):
        """初始化千问API客户端"""
        # 首先调用父类的初始化方法 (如果需要继承父类属性)
        # super().__init__() # 取消注释如果需要继承 QwenServiceBase 的 __init__

        # 从环境变量获取API密钥
        self.api_key = os.getenv("QWEN_API_KEY")
        api_key_masked = f"{self.api_key[:5]}...{self.api_key[-3:]}" if self.api_key else None
        logger.info(f"API密钥是否存在: {self.api_key is not None}, 掩码值: {api_key_masked}")
        
        # 使用国际版API端点
        self.api_base = os.getenv(
            "QWEN_API_BASE", 
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        logger.info(f"使用API端点: {self.api_base}")
        
        # 请求头
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info(f"初始化请求头: Content-Type={self.headers['Content-Type']}")
        
        # 配置requests会话
        self.session = requests.Session()
        # 设置重试策略
        retry_strategy = Retry(
            total=3,  # 最大重试次数
            backoff_factor=1,  # 重试间隔
            status_forcelist=[403, 429, 500, 502, 503, 504]  # 添加403到重试状态码列表
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        logger.info(f"配置重试策略: 最大重试={retry_strategy.total}, 退避因子={retry_strategy.backoff_factor}")
        
        # 添加 timeout 属性
        self.timeout = 120 # 设置默认请求超时时间（秒），与 QwenServiceBase 一致

        # 其他配置保持不变
        self.model = os.getenv("QWEN_MODEL", "qwen-max")
        logger.info(f"使用模型: {self.model}")
        
        self.vl_high_resolution_images = True
        self.max_tokens = 30720
        self.image_token_cost = 2118 if self.vl_high_resolution_images else 1227
        self.max_images = int(self.max_tokens * 0.8 / self.image_token_cost)
        logger.info(f"图像设置: 高分辨率={self.vl_high_resolution_images}, 最大token={self.max_tokens}, 图像token成本={self.image_token_cost}, 最大图像数={self.max_images}")
        
        # 初始化服务可用性状态
        self.available = False
        logger.info("开始检查服务可用性...")
        self._check_availability()
        logger.info(f"服务可用性检查完成，可用状态: {self.available}")
    
    def _check_availability(self):
        """检查服务是否可用"""
        if not self.api_key:
            logger.error("未设置QWEN_API_KEY环境变量")
            self.available = False
            return
        
        try:
            # 使用OpenAI兼容模式格式的测试请求 - 使用正确的消息格式
            test_payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system", 
                        "content": [{"type": "text", "text": "You are a helpful assistant."}]
                    },
                    {
                        "role": "user", 
                        "content": [{"type": "text", "text": "测试消息"}]
                    }
                ]
            }
            
            logger.info(f"发送测试请求到: {self.api_base}")
            logger.info(f"请求头: {self.headers}")
            logger.info(f"请求体: {test_payload}")
            
            # 首先尝试不使用会话直接请求
            try:
                direct_response = requests.post(
                    self.api_base,
                    headers=self.headers,
                    json=test_payload,
                    timeout=10,
                    verify=True
                )
                logger.info(f"直接请求响应状态码: {direct_response.status_code}")
                logger.info(f"直接请求响应内容: {direct_response.text}")
                
                if direct_response.status_code == 200:
                    logger.info("直接请求成功，千问API服务可用")
                    self.available = True
                    return
            except Exception as e:
                logger.warning(f"直接请求失败: {str(e)}")
                
            # 如果直接请求失败，尝试使用会话
            response = self.session.post(
                self.api_base,
                headers=self.headers,
                json=test_payload,
                timeout=10,
                verify=True
            )
            
            logger.info(f"会话请求响应状态码: {response.status_code}")
            logger.info(f"会话请求响应内容: {response.text}")
            
            if response.status_code == 200:
                logger.info("会话请求成功，千问API服务可用")
                self.available = True
            else:
                logger.error(f"千问API服务不可用，状态码: {response.status_code}")
                self.available = False
                
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL证书验证失败: {str(e)}")
            logger.error(f"尝试禁用SSL验证后重新请求")
            logger.error(f"SSL错误详情: {e.__class__.__name__}: {str(e)}")
            
            try:
                logger.info(f"使用禁用SSL验证的方式重新发送请求 - 时间: {datetime.datetime.now().isoformat()}")
                response = self.session.post(
                    self.api_base,
                    headers=self.headers,
                    json=test_payload,
                    timeout=60,
                    verify=False
                )
                logger.info(f"禁用SSL验证的请求响应状态码: {response.status_code}")
                
                if response.status_code == 200:
                    logger.info("千问API服务可用（禁用SSL验证）")
                    self.available = True
                else:
                    logger.error(f"千问API服务不可用，状态码: {response.status_code}")
                    self.available = False
            except Exception as e2:
                logger.error(f"服务可用性检查失败（禁用SSL验证后）: {str(e2)}")
                self.available = False
        except Exception as e:
            logger.error(f"服务可用性检查失败: {str(e)}")
            self.available = False

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.available and self.api_key is not None
    
    def _extract_scene_frames(self, video_path: str, max_frames: int = 5) -> List[Tuple[str, str]]:
        """
        使用场景检测从视频中提取关键帧
        
        Args:
            video_path: 视频文件路径
            max_frames: 最大提取帧数
            
        Returns:
            List[Tuple[str, str]]: 包含base64编码的图像和图像文件路径的元组列表
        """
        # 使用模型token限制来计算最大可提取的关键帧数量
        adaptive_max_frames = min(max_frames, self.max_images)
        
        try:
            from scenedetect import detect, ContentDetector, open_video
            
            logger.info("使用场景检测方法提取关键帧")
            
            # 使用固定的阈值7.0进行场景检测
            detector = ContentDetector(
                threshold=7.0,  # 设置固定阈值为7.0
                min_scene_len=15  # 最小场景长度（帧数）
            )
            
            logger.info(f"场景检测参数: 阈值=7.0, 最小场景长度=15帧")
            
            # 执行场景检测
            scenes = detect(video_path, detector)
            
            if not scenes:
                logger.warning("未检测到场景，将回退到均匀分段方法")
                return self._extract_uniform_frames(video_path, adaptive_max_frames)
            
            logger.info(f"成功检测到 {len(scenes)} 个场景")
            
            # 如果场景太多，选择平均分布的场景
            selected_scenes = []
            if len(scenes) <= adaptive_max_frames:
                selected_scenes = scenes
                logger.info(f"选择所有{len(scenes)}个场景")
            else:
                # 均匀选择场景
                step = len(scenes) / adaptive_max_frames
                logger.info(f"从{len(scenes)}个场景中均匀选择{adaptive_max_frames}个场景, 步长: {step:.2f}")
                
                for i in range(adaptive_max_frames):
                    idx = min(int(i * step), len(scenes) - 1)
                    selected_scenes.append(scenes[idx])
                    scene = scenes[idx]
                    start_time = scene[0].get_seconds()
                    end_time = scene[1].get_seconds()
                    logger.info(f"选择场景 {idx+1}: {start_time:.2f}s - {end_time:.2f}s")
            
            # 从每个选中的场景提取一个关键帧
            result = []
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            logger.info(f"从选中的{len(selected_scenes)}个场景中提取中间帧...")
            for i, scene in enumerate(selected_scenes):
                # 获取场景的中间帧
                start_frame = scene[0].get_frames()
                end_frame = scene[1].get_frames()
                middle_frame = start_frame + (end_frame - start_frame) // 2
                
                # 计算时间戳
                timestamp = middle_frame / float(fps) if fps > 0 else 0
                
                logger.info(f"场景 {i+1}: 提取中间帧 {middle_frame} (时间点: {timestamp:.2f}s)")
                
                # 设置到中间帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
                ret, frame = cap.read()
                
                if ret:
                    # 处理帧并转换为base64
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    from PIL import Image
                    import io
                    
                    # 直接使用原始分辨率的图片
                    pil_image = Image.fromarray(frame_rgb)
                    
                    # 根据高分辨率设置调整图像大小
                    if self.vl_high_resolution_images:
                        pil_image = pil_image.resize((1288, 1288), Image.LANCZOS)
                    else:
                        pil_image = pil_image.resize((980, 980), Image.LANCZOS)
                    
                    # 创建一个唯一的文件名
                    keyframe_filename = f"{uuid.uuid4()}_scene_{i}_frame_{middle_frame}.jpg"
                    keyframe_path = os.path.join(settings.KEYFRAMES_DIR, keyframe_filename)
                    
                    # 保存图像到文件
                    pil_image.save(keyframe_path, format="JPEG", quality=95)
                    
                    # 转换为base64
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format="JPEG", quality=95)
                    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    
                    result.append((img_base64, keyframe_path))
                    logger.info(f"成功提取场景中间帧(时间点: {timestamp:.2f}秒), base64长度: {len(img_base64)}, 保存路径: {keyframe_path}")
                else:
                    logger.warning(f"无法读取帧 {middle_frame}")
            
            cap.release()
            logger.info(f"场景检测完成: 成功从{len(selected_scenes)}个场景中提取了{len(result)}个关键帧")
            
            return result
            
        except Exception as e:
            logger.error(f"使用场景检测提取关键帧时出错: {str(e)}")
            logger.info(f"回退到均匀分段方法...")
            return self._extract_uniform_frames(video_path, adaptive_max_frames)
    
    def generate_summary_from_video(self, video_url: str, audio_url: Optional[str] = None, granularity: str = "medium",
                                format_markdown: bool = False, video_metadata: Optional[Dict[str, Any]] = None,
                                audio_transcript: Optional[str] = None, transcription_result: Optional[Dict[str, Any]] = None,
                                keyframe_method: str = "uniform", num_frames: int = 5, interval_seconds: int = 10,
                                language: str = "zh") -> Dict[str, Any]:
        """从视频生成摘要，使用 GCS URL"""
        logger.info("========== 开始生成视频摘要 (使用 GCS URL) ==========")
        logger.info(f"视频文件路径/URL: {video_url}") # 注意：这里传入的 video_url 应该是本地路径或可访问的URL，用于提取帧
        logger.info(f"参数: granularity={granularity}, format_markdown={format_markdown}, keyframe_method={keyframe_method}, num_frames={num_frames}, interval_seconds={interval_seconds}, language={language}")

        if not self.is_available() or not self.api_key:
            logger.error("千问API服务不可用或密钥未设置，无法生成摘要")
            return {"error": "Qwen API service is unavailable or API key is not set", "summary_text": "", "keyframes": []}

        # 检查传入的 video_url 是否是纯音频文件 (如果是，则不提取关键帧)
        is_audio_only = False
        if isinstance(video_url, str) and (video_url.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg'))):
            logger.info(f"检测到输入是纯音频文件: {video_url}")
            is_audio_only = True

        # 提取视频关键帧并获取 GCS URL (如果不是纯音频)
        gcs_image_urls: List[str] = []
        if not is_audio_only:
            logger.info(f"开始提取视频关键帧并上传到 GCS，使用方法: {keyframe_method}")
            try:
                # 调用 QwenService (part1) 中的 extract_key_frames
                # 这里的 video_url 应该是可以被 ffmpeg/opencv 读取的本地路径或 URL
                gcs_image_urls = self.extract_key_frames(
                    video_path=video_url,
                    method=keyframe_method,
                    num_frames=num_frames, # 内部会根据 token 限制调整
                    interval_seconds=interval_seconds
                )
                if gcs_image_urls:
                    logger.info(f"成功获取 {len(gcs_image_urls)} 个 GCS 关键帧 URL/URI")
                    # for i, url in enumerate(gcs_image_urls):
                    #     logger.info(f"关键帧 {i+1} URL/URI: {url}")
                else:
                    logger.warning("未能从视频中提取或上传关键帧")
            except Exception as extract_err:
                 logger.error(f"提取/上传关键帧时发生严重错误: {extract_err}", exc_info=True)
                 # 根据错误处理策略，可以选择继续（无图像）或失败
                 # return {"error": f"Failed to extract/upload keyframes: {extract_err}", "summary_text": "", "keyframes": []}
                 logger.warning("将继续尝试生成摘要，但不包含图像信息")

        # 过滤掉非 HTTP/HTTPS 的 URL (例如 gs:// URI)，因为API可能不支持
        http_image_urls = [url for url in gcs_image_urls if url.startswith("http")]
        if len(http_image_urls) < len(gcs_image_urls):
             logger.warning(f"移除了 {len(gcs_image_urls) - len(http_image_urls)} 个非 HTTP/HTTPS 的 GCS URL (例如 gs:// URIs)")

        # 检查是否至少有文本信息可用
        if not http_image_urls and not audio_transcript and not video_metadata:
             logger.error("无法生成摘要: 没有有效的图像 URL，也没有音频转录或元数据")
             return {
                 "error": "No valid image URLs, audio transcript, or metadata available to generate summary.",
                 "summary_text": "",
                 "keyframes": [os.path.basename(url) for url in gcs_image_urls] # 仍然返回原始 GCS 路径或 URI
             }

        # 构建系统提示词 (保持不变)
        system_prompts = {
            "en": {
                "short": "You are a professional video analyst skilled at extracting key information from images and audio transcripts to generate concise summaries. Please generate a summary of no more than 200 words.",
                "medium": "You are a professional video analyst skilled at extracting key information from images and audio transcripts to generate summaries. Please provide a summary that includes main content, key points, and conclusions.",
                "detailed": "You are a professional video analyst skilled at extracting detailed information from images and audio transcripts to generate comprehensive summaries. Please describe the video content in as much detail as possible."
            },
            "zh": {
                "short": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成简洁的摘要。请生成不超过200字的简短摘要。",
                "medium": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。请提供一个包含主要内容、关键点和结论的摘要。",
                "detailed": "你是一位专业的视频分析师，善于从图像和音频转录中提取详细信息并生成全面的摘要。请尽可能详细地描述视频内容。"
            }
        }
        system_content = system_prompts.get(language, system_prompts["zh"])[granularity] # 默认中文
        logger.info(f"使用系统提示词 (语言: {language}, 粒度: {granularity})")

        # 构建用户消息内容列表
        user_content = []
        # 添加图像URL - 使用正确的格式
        if http_image_urls:
            for image_url in http_image_urls:
                if image_url.startswith(("http://", "https://")):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    })
                    logger.info(f"添加图像URL: {image_url}")
                else:
                    logger.warning(f"无效的图像URL (非HTTP/HTTPS): {image_url}")
        else:
            logger.info("没有关键帧图像URL可添加")

        # 添加文本内容 (提示词, 音频转录, 视频元数据)
        text_parts = []
        if audio_transcript:
            # 截断过长的转录文本以避免超出 token 限制
            max_transcript_len = 10000 # 示例：限制转录文本最大长度
            truncated_transcript = audio_transcript
            if len(audio_transcript) > max_transcript_len:
                 truncated_transcript = audio_transcript[:max_transcript_len] + "... (转录文本已截断)"
                 logger.warning(f"音频转录文本过长 ({len(audio_transcript)} 字符)，已截断为 {max_transcript_len} 字符")
            text_parts.append(f"音频转录文本：\n{truncated_transcript}")
            logger.info(f"添加音频转录文本，长度: {len(truncated_transcript)} (处理后)")

        if video_metadata:
            # ... (metadata formatting and truncation logic remains the same)
            formatted_metadata = "\n\n视频元数据：\n"
            relevant_keys = ["title", "channel", "duration", "upload_date", "categories", "tags", "description"]
            filtered_metadata = {k: v for k, v in video_metadata.items() if k in relevant_keys and v}
            if "description" in filtered_metadata:
                 max_desc_len = 1000
                 if len(filtered_metadata["description"]) > max_desc_len:
                      filtered_metadata["description"] = filtered_metadata["description"][:max_desc_len] + "... (描述已截断)"
                      logger.warning(f"视频描述过长，已截断为 {max_desc_len} 字符")
            for key, value in filtered_metadata.items():
                formatted_metadata += f"{key}: {value}\n"
            text_parts.append(f"\n\n视频元数据:\n{formatted_metadata}")
            logger.info(f"添加视频元数据，键: {list(video_metadata.keys())}")

        if text_parts:
            # 添加最终指令
            final_instruction = f"\n\n请根据以上信息，生成一份语言为 '{language}'、粒度为 '{granularity}' 的视频摘要。"
            if format_markdown:
                final_instruction += "\n请使用 Markdown 格式输出摘要。"
            text_parts.append(final_instruction)

            # 合并所有文本部分
            full_text_content = "".join(text_parts)
            user_content.append({
                "type": "text",
                "text": full_text_content
            })
            logger.info(f"最终构建的提示文本长度: {len(full_text_content)}")

        # 准备发送到API的最终请求结构 - 使用正确的格式
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_content}]
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ]
        }

        # 记录准备发送的请求结构
        request_structure_log = {
            "model": payload["model"],
            "messages": [
                {
                    "role": msg["role"],
                    "content_type": "text" if msg["role"] == "system" else "multimodal",
                    "content_length": len(msg["content"]) if isinstance(msg["content"], str) else len(msg["content"])
                }
                for msg in payload.get("messages", [])
            ]
        }
        logger.info(f"准备发送到千问 API 的请求结构: {json.dumps(request_structure_log, indent=2)}")

        start_time = time.time()
        logger.info(f"开始发送 API 请求到: {self.api_base}")
        log_api_request(payload=payload, headers=self.headers) # 记录请求，隐藏API密钥

        try:
            # 发送请求
            response = self.session.post(
                self.api_base,
                headers=self.headers,
                json=payload,  # 直接使用 payload
                timeout=self.timeout
            )
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"API 请求完成 - 耗时: {duration:.2f}秒, 状态码: {response.status_code}")
            # 修正log_api_response调用，传入正确的参数
            log_api_response(self.api_base, response.status_code, response.text, duration)

            response.raise_for_status() # 如果状态码不是2xx，则抛出HTTPError异常

            # 解析响应
            response_data = response.json()

            # 记录成功响应的摘要内容 (如果存在)
            if response_data.get("choices") and response_data["choices"][0].get("message"):
                summary_content = response_data["choices"][0]["message"].get("content", "无摘要内容")
                logger.info(f"成功从API获取摘要: {summary_content[:100]}...") # 只记录摘要开头部分
            else:
                logger.warning("API响应中未找到预期的摘要内容")

            return {"summary": response_data, "status": "success"}

        except requests.exceptions.Timeout as e:
            end_time = time.time()
            duration = end_time - start_time
            error_msg = f"API 请求超时: {e}"
            logger.error(error_msg)
            # 修正log_api_error调用
            log_api_error(e, f"API请求超时 ({self.api_base})")
            return {"error": error_msg, "status": "error"}
        except requests.exceptions.RequestException as e:
             # RequestException 可能没有明确的 duration，但可以记录错误发生时间点
             error_msg = f"调用千问 API 时发生网络错误: {e}"
             logger.error(error_msg, exc_info=True)
             # 修正log_api_error调用
             log_api_error(e, f"网络错误 ({self.api_base})")
             return {"error": error_msg, "status": "error"}
        except Exception as e:
            # 其他异常，也记录近似的 duration
            error_msg = f"处理千问 API 响应时发生意外错误: {e}"
            logger.error(error_msg, exc_info=True)
            # 修正log_api_error调用
            log_api_error(e, f"意外错误 ({self.api_base})")
            return {"error": error_msg, "status": "error"}
        finally:
             logger.info("========== 结束生成视频摘要 ==========")

    def generate_summary_from_frames(
        self, 
        http_image_urls: List[str], 
        audio_transcript: Optional[str] = None, 
        video_metadata: Optional[Dict] = None,
        language: str = "zh",
        granularity: str = "medium",
        format_markdown: bool = True
    ) -> Dict[str, Any]:
        """
        从视频关键帧HTTP URL列表、音频转录和视频元数据生成摘要
        
        Args:
            http_image_urls: HTTP图像URL列表
            audio_transcript: 音频转录文本 (可选)
            video_metadata: 视频元数据字典 (可选)
            language: 摘要语言 ('zh' 或 'en')
            granularity: 摘要粒度 ('short', 'medium', 或 'detailed')
            format_markdown: 是否使用Markdown格式
            
        Returns:
            包含摘要或错误信息的字典
        """
        logger.info(f"开始从 {len(http_image_urls)} 个HTTP图像URL生成摘要，语言={language}, 粒度={granularity}")
        
        if not self.available:
            error_msg = "千问API服务不可用"
            logger.error(error_msg)
            return {"error": error_msg, "status": "error"}
        
        # 构建系统提示词
        system_prompts = {
            "en": {
                "short": "You are a professional video analyst skilled at extracting key information from images and audio transcripts to generate concise summaries. Please generate a summary of no more than 200 words.",
                "medium": "You are a professional video analyst skilled at extracting key information from images and audio transcripts to generate summaries. Please provide a summary that includes main content, key points, and conclusions.",
                "detailed": "You are a professional video analyst skilled at extracting detailed information from images and audio transcripts to generate comprehensive summaries. Please describe the video content in as much detail as possible."
            },
            "zh": {
                "short": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成简洁的摘要。请生成不超过200字的简短摘要。",
                "medium": "你是一位专业的视频分析师，善于从图像和音频转录中提取关键信息并生成摘要。请提供一个包含主要内容、关键点和结论的摘要。",
                "detailed": "你是一位专业的视频分析师，善于从图像和音频转录中提取详细信息并生成全面的摘要。请尽可能详细地描述视频内容。"
            }
        }
        system_content = system_prompts.get(language, system_prompts["zh"])[granularity] # 默认中文
        logger.info(f"使用系统提示词 (语言: {language}, 粒度: {granularity})")
        
        # 构建用户消息内容
        user_content = []
        
        # 添加图像URL，使用OpenAI兼容格式
        if http_image_urls:
            for image_url in http_image_urls:
                if image_url.startswith(("http://", "https://")):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    })
                    logger.info(f"添加图像URL: {image_url}")
                else:
                    logger.warning(f"无效的图像URL (非HTTP/HTTPS): {image_url}")
            
            if not any(isinstance(item, dict) and "type" in item and item["type"] == "image_url" for item in user_content):
                logger.warning("没有有效的HTTP/HTTPS图像URL添加到用户内容")
        else:
            logger.info("没有关键帧图像URL可添加")
        
        # 添加文本内容
        text_parts = []
        if audio_transcript:
            # 截断过长的转录文本以避免超出token限制
            max_transcript_len = 10000
            truncated_transcript = audio_transcript
            if len(audio_transcript) > max_transcript_len:
                truncated_transcript = audio_transcript[:max_transcript_len] + "... (转录文本已截断)"
                logger.warning(f"音频转录文本过长 ({len(audio_transcript)} 字符)，已截断为 {max_transcript_len} 字符")
            text_parts.append(f"音频转录文本：\n{truncated_transcript}")
            logger.info(f"添加音频转录文本，长度: {len(truncated_transcript)} (处理后)")
        
        if video_metadata:
            formatted_metadata = "\n\n视频元数据：\n"
            relevant_keys = ["title", "channel", "duration", "upload_date", "categories", "tags", "description"]
            filtered_metadata = {k: v for k, v in video_metadata.items() if k in relevant_keys and v}
            if "description" in filtered_metadata:
                max_desc_len = 1000
                if len(filtered_metadata["description"]) > max_desc_len:
                    filtered_metadata["description"] = filtered_metadata["description"][:max_desc_len] + "... (描述已截断)"
                    logger.warning(f"视频描述过长，已截断为 {max_desc_len} 字符")
            for key, value in filtered_metadata.items():
                formatted_metadata += f"{key}: {value}\n"
            text_parts.append(f"\n\n视频元数据:\n{formatted_metadata}")
            logger.info(f"添加视频元数据，键: {list(video_metadata.keys())}")
        
        if text_parts:
            # 添加最终指令
            final_instruction = f"\n\n请根据以上信息，生成一份语言为 '{language}'、粒度为 '{granularity}' 的视频摘要。"
            if format_markdown:
                final_instruction += "\n请使用 Markdown 格式输出摘要。"
            text_parts.append(final_instruction)
            
            # 合并所有文本部分并添加到用户内容
            full_text_content = "".join(text_parts)
            user_content.append({
                "type": "text",
                "text": full_text_content
            })
            logger.info(f"最终构建的提示文本长度: {len(full_text_content)}")
        
        # 准备API请求，使用OpenAI兼容格式
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_content}]
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ]
        }
        
        # 记录请求结构日志
        request_structure_log = {
            "model": payload["model"],
            "messages": [
                {
                    "role": msg["role"],
                    "content_type": "array",
                    "content_length": len(msg["content"])
                }
                for msg in payload.get("messages", [])
            ]
        }
        logger.info(f"准备发送到千问API的请求结构: {json.dumps(request_structure_log, indent=2)}")
        
        start_time = time.time()
        logger.info(f"开始发送API请求到: {self.api_base}")
        log_api_request(payload=payload, headers=self.headers)
        
        try:
            # 发送请求
            response = self.session.post(
                self.api_base,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"API请求完成 - 耗时: {duration:.2f}秒, 状态码: {response.status_code}")
            log_api_response(self.api_base, response.status_code, response.text, duration)
            
            response.raise_for_status()
            
            # 解析响应
            response_data = response.json()
            
            # 提取摘要内容
            if response_data.get("choices") and response_data["choices"][0].get("message"):
                summary_content = response_data["choices"][0]["message"].get("content", "无摘要内容")
                logger.info(f"成功从API获取摘要: {summary_content[:100]}...")
            else:
                logger.warning("API响应中未找到预期的摘要内容")
            
            return {"summary": response_data, "status": "success"}
            
        except requests.exceptions.Timeout as e:
            end_time = time.time()
            duration = end_time - start_time
            error_msg = f"API请求超时: {e}"
            logger.error(error_msg)
            log_api_error(e, f"API请求超时 ({self.api_base})")
            return {"error": error_msg, "status": "error"}
        except requests.exceptions.RequestException as e:
            error_msg = f"调用千问API时发生网络错误: {e}"
            logger.error(error_msg, exc_info=True)
            log_api_error(e, f"网络错误 ({self.api_base})")
            return {"error": error_msg, "status": "error"}
        except Exception as e:
            error_msg = f"处理千问API响应时发生意外错误: {e}"
            logger.error(error_msg, exc_info=True)
            log_api_error(e, f"意外错误 ({self.api_base})")
            return {"error": error_msg, "status": "error"}
        finally:
            logger.info("========== 结束生成视频摘要 ==========")

    def generate_summary(self, video_url: str, transcription: Optional[str] = None, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """生成视频摘要"""
        try:
            logger.info(f"开始生成视频摘要，视频URL: {video_url}")
            
            # 提取关键帧 - 这里会调用父类的方法
            frame_result = self.extract_key_frames(video_url)
            
            # 检查关键帧提取是否成功
            if "error" in frame_result:
                logger.error(f"提取关键帧失败: {frame_result['error']}")
                return frame_result
            
            # 获取HTTP图像URL列表
            http_image_urls = frame_result.get("frame_urls", [])
            if not http_image_urls:
                logger.warning("未提取到有效的关键帧URL")
            
            # 使用新的generate_summary_from_frames方法生成摘要
            return self.generate_summary_from_frames(
                http_image_urls=http_image_urls,
                audio_transcript=transcription,
                video_metadata=metadata,
                language="zh",  # 默认中文
                granularity="medium",  # 默认中等详细度
                format_markdown=True  # 默认使用Markdown格式
            )
                
        except Exception as e:
            error_msg = f"生成摘要时出错 (generate_summary): {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}

# 创建千问服务实例
qwen_service = QwenService() 