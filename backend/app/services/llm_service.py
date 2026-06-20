"""
阿里云 Qwen3-VL 多模态视频总结服务（双模型架构）
- Qwen3-VL-Flash (qwen-vl-max): 用于关键帧图像分析
- Qwen3-VL-Plus (qwen-vl-plus): 用于主视频总结生成
支持基于关键帧图像和转录文本的智能总结

安全更新 (2025-12):
- 多模态图像分析功能已禁用（ENABLE_MULTIMODAL_ANALYSIS=False）
- 系统改为基于逐字稿的纯文本分析
- 关键帧分析方法保留但默认返回空结果
"""
import os
import json
import re
import logging
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

import dashscope
from dashscope import MultiModalConversation, Generation

from ..core.config import settings
from ..core.logging import logger
from ..models.video import KeyframeInfo
from ..models.analysis import (
    TranscriptMetadata, 
    KeyframeMetadata, 
    VideoSummary,
    KeyframeDescription as KeyframeDescriptionModel
)

# 安全配置开关
ENABLE_MULTIMODAL_ANALYSIS = os.getenv("ENABLE_MULTIMODAL_ANALYSIS", "false").lower() == "true"
ENABLE_KEYFRAME_EXTRACTION = os.getenv("ENABLE_KEYFRAME_EXTRACTION", "false").lower() == "true"


@dataclass
class KeyframeDescription:
    """单个关键帧的分析描述（用于旧版兼容）"""
    frame_id: int
    timestamp: float
    description: str
    oss_image_url: str
    confidence: float


@dataclass
class SummarySection:
    """基于时间线的总结段落"""
    start_time: float
    end_time: float
    title: str
    content: str
    keyframe_ids: List[int]  # 关联的关键帧ID


@dataclass
class VideoSummaryOld:
    """完整的视频总结（旧版本，保留用于向后兼容）"""
    video_id: str
    brief_summary: str  # 简要总结(1-2句话)
    standard_summary: str  # 标准总结(段落级)
    detailed_summary: Optional[str]  # 详细总结(分段详解)
    sections: List[SummarySection]  # 时间线段落
    keyframe_descriptions: List[KeyframeDescription]  # 关键帧描述
    language: str  # 总结语言
    generated_at: str  # 生成时间


class QwenVLService:
    """
    阿里云 Qwen3-VL 多模态服务（双模型架构）
    - vision_model (qwen-vl-max): Qwen3-VL-Flash，专用于图像分析
    - text_model (qwen-vl-plus): Qwen3-VL-Plus，专用于文本总结
    """
    
    def __init__(self):
        """初始化 Qwen VL 服务"""
        # 从环境变量获取 API 密钥
        # 优先使用 QWEN_API_KEY，与现有配置保持一致
        self.api_key = (
            os.getenv("QWEN_API_KEY") or 
            os.getenv("DASHSCOPE_API_KEY")
        )
        
        # 设置 DashScope API 密钥
        if self.api_key:
            os.environ["DASHSCOPE_API_KEY"] = self.api_key
            dashscope.api_key = self.api_key
            logger.info("Qwen VL 服务使用 QWEN_API_KEY 初始化")

        # 支持自定义 DashScope base URL
        if settings.DASHSCOPE_HTTP_BASE_URL:
            os.environ["DASHSCOPE_HTTP_BASE_URL"] = settings.DASHSCOPE_HTTP_BASE_URL
            dashscope.base_http_api_url = settings.DASHSCOPE_HTTP_BASE_URL
            logger.info(f"DashScope HTTP endpoint: {settings.DASHSCOPE_HTTP_BASE_URL}")
        
        # 模型配置（在检查可用性之前定义）
        self.vision_model = settings.VISION_MODEL
        self.text_model = settings.VISION_SUMMARY_MODEL
        self.temperature = 0.7  # 创造性和准确性的平衡
        self.max_tokens = 2000  # 最大输出长度
        
        # 检查可用性
        if not self.api_key:
            logger.warning("Qwen API 密钥未设置，请设置环境变量: QWEN_API_KEY 或 DASHSCOPE_API_KEY")
            self.available = False
        else:
            self.available = True
            logger.info(f"Qwen3-VL 服务初始化成功 - Vision: {self.vision_model}, Text: {self.text_model}")
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.available and bool(self.api_key)
    
    async def analyze_keyframe(self, image_url: str, context: str = "", max_retries: int = 3) -> Optional[str]:
        """
        分析单个关键帧，生成描述（带重试机制）
        
        安全更新：此功能已默认禁用，需设置 ENABLE_MULTIMODAL_ANALYSIS=true 启用
        
        Args:
            image_url: 关键帧的 OSS 图片 URL
            context: 上下文信息(如转录文本)
            max_retries: 最大重试次数
            
        Returns:
            关键帧描述文本
        """
        # 检查多模态分析是否启用
        if not ENABLE_MULTIMODAL_ANALYSIS:
            logger.info("多模态分析已禁用 (ENABLE_MULTIMODAL_ANALYSIS=false)")
            return None
        
        if not self.is_available():
            logger.error("Qwen VL 服务不可用")
            return None
        
        # 构建提示词
        prompt = "请详细描述这个视频关键帧中的内容，包括场景、人物、动作和关键元素。"
        if context:
            prompt += f"\n\n相关上下文：{context[:500]}"  # 限制上下文长度
        
        # 构建消息
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": image_url},
                    {"text": prompt}
                ]
            }
        ]
        
        # 重试机制
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # 重试前等待，使用指数退避策略
                    wait_time = 2 ** attempt  # 2秒, 4秒, 8秒...
                    logger.warning(f"第 {attempt + 1}/{max_retries} 次重试，等待 {wait_time} 秒...")
                    await asyncio.sleep(wait_time)
                
                logger.info(f"分析关键帧: {image_url}")
                
                # 调用 API (使用 asyncio 包装同步调用)
                # 使用 vision_model (qwen-vl-max) 进行图像分析
                response = await asyncio.to_thread(
                    MultiModalConversation.call,
                    model=self.vision_model,
                    messages=messages,
                    temperature=self.temperature,
                    max_length=500  # 单个关键帧描述较短
                )
                
                # 检查响应
                if not response or response.status_code != 200:
                    error_msg = f"API 调用失败: {response.message if response else 'No response'}"
                    logger.error(error_msg)
                    if attempt < max_retries - 1:
                        continue  # 重试
                    return None
                
                # 提取描述文本
                if hasattr(response, 'output') and hasattr(response.output, 'choices'):
                    content = response.output.choices[0].message.content
                    
                    # 处理 API 返回格式：可能是字符串或列表
                    if isinstance(content, list):
                        # 如果是列表格式 [{'text': '...'}]，提取第一个元素的 text
                        description = content[0].get('text', '') if content else ''
                    elif isinstance(content, str):
                        description = content
                    else:
                        logger.error(f"API 返回了未知的 content 格式: {type(content)}")
                        if attempt < max_retries - 1:
                            continue  # 重试
                        return None
                    
                    logger.info(f"关键帧分析成功，描述长度: {len(description)} 字符")
                    logger.info(f"描述内容: {description[:200]}...")  # 只显示前200字符
                    return description
                else:
                    logger.error("API 响应格式异常")
                    if attempt < max_retries - 1:
                        continue  # 重试
                    return None
                    
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                
                # 判断是否为网络相关错误（可重试）
                is_network_error = any([
                    'SSL' in error_msg,
                    'Connection' in error_msg,
                    'Timeout' in error_msg,
                    'Max retries' in error_msg
                ])
                
                if is_network_error and attempt < max_retries - 1:
                    logger.warning(f"网络错误 ({error_type}): {error_msg}，将重试...")
                    continue  # 重试
                else:
                    logger.exception(f"关键帧分析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        return None  # 最后一次尝试也失败，返回 None
        
        return None  # 所有重试都失败
    
    async def generate_video_summary(
        self,
        keyframes: List[KeyframeMetadata],
        transcription: TranscriptMetadata,
        video_id: str,
        granularity: str = "standard"
    ) -> Optional[VideoSummaryOld]:
        """
        生成完整的视频总结（旧版本，保留用于向后兼容）
        
        Args:
            keyframes: 关键帧列表
            transcription: 转录元数据
            video_id: 视频 ID
            granularity: 总结粒度 ("brief", "standard", "detailed")
            
        Returns:
            视频总结对象
        """
        if not self.is_available():
            logger.error("Qwen VL 服务不可用")
            return None
        
        try:
            logger.info(f"开始生成视频总结，粒度: {granularity}")
            
            # 步骤 1: 分析关键帧
            keyframe_descriptions = await self._analyze_keyframes_batch(
                keyframes, transcription
            )
            
            # 步骤 2: 生成不同粒度的总结
            summaries = await self._generate_summaries_by_granularity(
                keyframe_descriptions, transcription, granularity
            )
            
            # 步骤 3: 生成时间线段落
            sections = await self._generate_timeline_sections(
                keyframe_descriptions, transcription
            )
            
            # 构建最终总结对象（使用旧版本结构）
            video_summary = VideoSummaryOld(
                video_id=video_id,
                brief_summary=summaries.get("brief", ""),
                standard_summary=summaries.get("standard", ""),
                detailed_summary=summaries.get("detailed") if granularity == "detailed" else None,
                sections=sections,
                keyframe_descriptions=keyframe_descriptions,
                language=transcription.language,
                generated_at=datetime.now().isoformat()
            )
            
            logger.info(f"视频总结生成成功，包含 {len(keyframe_descriptions)} 个关键帧描述和 {len(sections)} 个段落")
            return video_summary
            
        except Exception as e:
            logger.exception(f"生成视频总结失败: {e}")
            return None
    
    async def generate_text_based_summary(
        self,
        transcript: TranscriptMetadata,
        video_metadata: Dict[str, Any],
        video_id: str
    ) -> Optional[VideoSummary]:
        """
        基于转录文本和视频元数据生成详细总结（v0.2.0 新增）
        使用 qwen3-max 模型，仅处理文本，不包含图像分析
        
        Args:
            transcript: 转录元数据（包含完整的音频文本）
            video_metadata: 视频元数据（来自 ffprobe）
            video_id: 视频标识
            
        Returns:
            VideoSummary 对象（仅包含 detailed_summary 字段）
        """
        if not self.is_available():
            logger.error("Qwen VL 服务不可用")
            return None
        
        try:
            logger.info(f"开始生成基于文本的视频总结: {video_id}")
            
            # 步骤 1: 提取视频元信息
            video_title = video_metadata.get("title", "未知标题")
            video_duration = video_metadata.get("duration", 0)
            video_description = video_metadata.get("description", "")
            video_uploader = video_metadata.get("uploader", "")
            
            # 格式化时长
            duration_str = self._format_duration(video_duration)
            
            # 步骤 2: 拼接所有转录片段文本
            if not transcript or not transcript.segments:
                logger.warning("转录文本为空，无法生成总结")
                return None
            
            full_transcript_text = " ".join([seg.text for seg in transcript.segments])
            logger.info(f"完整转录文本长度: {len(full_transcript_text)} 字符")
            
            # 步骤 3: 构建提示词
            prompt = f"""基于以下视频的元信息和完整转录文本，生成一份详细的内容总结：

视频元信息：
- 标题：{video_title}
- 时长：{duration_str}
"""
            
            if video_description:
                # 限制描述长度
                desc_preview = video_description[:500] + "..." if len(video_description) > 500 else video_description
                prompt += f"- 描述：{desc_preview}\n"
            
            if video_uploader:
                prompt += f"- 上传者/来源：{video_uploader}\n"
            
            prompt += f"""
完整转录文本：
{full_transcript_text}

总结要求：
1. 涵盖视频的核心主题和目标
2. 按逻辑结构组织要点（如引言、主体、结论）
3. 提取关键信息和亮点
4. 使用清晰的段落形式
5. 根据视频内容语言自动选择总结语言（中文视频用中文总结，英文视频用英文总结）
6. 总结长度根据视频内容复杂度灵活调整，确保信息完整性
"""
            
            logger.info(f"提示词长度: {len(prompt)} 字符")
            
            # 步骤 4: 调用摘要模型 API
            detailed_summary = await self._call_text_generation(
                prompt=prompt,
                max_tokens=2000,  # 增加以支持灵活长度
                model=settings.LLM_SUMMARY_MODEL  # 摘要模型（config 集中配置）
            )
            
            if not detailed_summary:
                logger.error("文本总结生成失败")
                return None
            
            # 步骤 5: 创建 VideoSummary 对象
            video_summary = VideoSummary(
                video_id=video_id,
                detailed_summary=detailed_summary
            )
            
            logger.info(f"文本总结生成成功，长度: {len(detailed_summary)} 字符")
            return video_summary
            
        except Exception as e:
            logger.exception(f"生成文本总结失败: {e}")
            return None
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时长"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if secs > 0 or not parts:
            parts.append(f"{secs}秒")
        
        return " ".join(parts)
    
    async def analyze_keyframes_multimodal(
        self,
        keyframes: List[KeyframeMetadata],
        context: Optional[str] = None
    ) -> List[KeyframeDescriptionModel]:
        """
        多模态关键帧分析服务（独立服务，v0.2.0 新增）
        按需调用，不在主流水线中执行
        
        安全更新：此功能已默认禁用，需设置 ENABLE_MULTIMODAL_ANALYSIS=true 启用
        
        Args:
            keyframes: 关键帧列表（含 OSS URL）
            context: 可选的上下文文本
            
        Returns:
            关键帧描述列表
        """
        # 检查多模态分析是否启用
        if not ENABLE_MULTIMODAL_ANALYSIS:
            logger.info("多模态关键帧分析已禁用 (ENABLE_MULTIMODAL_ANALYSIS=false)")
            return []
        
        if not self.is_available():
            logger.error("Qwen VL 服务不可用")
            return []
        
        try:
            logger.info(f"开始多模态关键帧分析，关键帧数量: {len(keyframes)}")
            
            keyframe_descriptions = []
            
            # 限制并发数量，避免 API 限流
            max_concurrent = 3
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def analyze_single_keyframe(kf: KeyframeMetadata) -> Optional[KeyframeDescriptionModel]:
                """分析单个关键帧"""
                async with semaphore:
                    description_text = await self.analyze_keyframe(
                        kf.oss_image_url, 
                        context or ""
                    )
                    
                    if description_text:
                        return KeyframeDescriptionModel(
                            frame_id=kf.frame_id,
                            timestamp=kf.timestamp,
                            description=description_text,
                            oss_image_url=kf.oss_image_url,
                            confidence=0.85  # 固定置信度
                        )
                    return None
            
            # 并发分析所有关键帧
            tasks = [analyze_single_keyframe(kf) for kf in keyframes]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 过滤成功的结果
            for result in results:
                if isinstance(result, KeyframeDescriptionModel):
                    keyframe_descriptions.append(result)
                elif isinstance(result, Exception):
                    logger.warning(f"关键帧分析失败: {result}")
            
            logger.info(f"成功分析 {len(keyframe_descriptions)}/{len(keyframes)} 个关键帧")
            return keyframe_descriptions
            
        except Exception as e:
            logger.exception(f"多模态关键帧分析失败: {e}")
            return []
    
    async def _analyze_keyframes_batch(
        self,
        keyframes: List[KeyframeMetadata],
        transcription: TranscriptMetadata
    ) -> List[KeyframeDescription]:
        """
        批量分析关键帧
        
        Args:
            keyframes: 关键帧列表
            transcription: 转录数据，用于提供上下文
            
        Returns:
            关键帧描述列表
        """
        keyframe_descriptions = []
        
        # 准备转录文本作为上下文
        transcript_text = " ".join([seg.text for seg in transcription.segments]) if transcription.segments else ""
        
        # 限制并发数量，避免 API 限流
        max_concurrent = 3
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_single_keyframe(kf: KeyframeMetadata) -> Optional[KeyframeDescription]:
            """分析单个关键帧"""
            async with semaphore:
                # 找到关键帧时间附近的转录文本作为上下文
                context = self._get_context_for_timestamp(
                    kf.timestamp, transcription.segments, window=30.0
                )
                
                # 如果没有特定上下文，使用完整转录的前500字符
                if not context and transcript_text:
                    context = transcript_text[:500]
                
                description_text = await self.analyze_keyframe(kf.oss_image_url, context)
                
                if description_text:
                    return KeyframeDescription(
                        frame_id=kf.frame_id,
                        timestamp=kf.timestamp,
                        description=description_text,
                        oss_image_url=kf.oss_image_url,
                        confidence=0.85  # 固定置信度，可以后续优化
                    )
                return None
        
        # 并发分析所有关键帧
        tasks = [analyze_single_keyframe(kf) for kf in keyframes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤成功的结果
        for result in results:
            if isinstance(result, KeyframeDescription):
                keyframe_descriptions.append(result)
            elif isinstance(result, Exception):
                logger.warning(f"关键帧分析失败: {result}")
        
        logger.info(f"成功分析 {len(keyframe_descriptions)}/{len(keyframes)} 个关键帧")
        return keyframe_descriptions
    
    def _get_context_for_timestamp(
        self,
        timestamp: float,
        segments: List,
        window: float = 30.0
    ) -> str:
        """
        获取时间戳附近的转录文本作为上下文
        
        Args:
            timestamp: 时间戳(秒)
            segments: 转录段落列表
            window: 时间窗口(秒)，前后各取 window/2
            
        Returns:
            上下文文本
        """
        context_segments = []
        
        for seg in segments:
            # 检查段落是否在时间窗口内
            if (seg.start_time <= timestamp + window/2 and 
                seg.end_time >= timestamp - window/2):
                context_segments.append(seg.text)
        
        return " ".join(context_segments)
    
    async def _generate_summaries_by_granularity(
        self,
        keyframe_descriptions: List[KeyframeDescription],
        transcription: TranscriptMetadata,
        granularity: str
    ) -> Dict[str, str]:
        """
        根据粒度生成不同层级的总结
        
        Args:
            keyframe_descriptions: 关键帧描述列表
            transcription: 转录数据
            granularity: 总结粒度
            
        Returns:
            包含不同粒度总结的字典
        """
        # 准备素材 - 使用完整转录文本而非截断
        transcript_text = " ".join([seg.text for seg in transcription.segments]) if transcription.segments else ""
        
        # 智能截取转录文本：优先保留开头和结尾，因为它们通常包含关键信息
        def smart_truncate_transcript(text: str, max_length: int) -> str:
            """智能截断转录文本，保留开头和结尾"""
            if len(text) <= max_length:
                return text
            
            # 如果文本过长，取开头60%和结尾40%
            head_length = int(max_length * 0.6)
            tail_length = int(max_length * 0.4)
            
            return text[:head_length] + "\n...\n" + text[-tail_length:]
        
        # 使用所有关键帧描述（不限制数量）
        keyframe_texts = "\n".join([
            f"[{kf.timestamp:.1f}s] {kf.description}" 
            for kf in keyframe_descriptions
        ])
        
        summaries = {}
        
        # 生成简要总结 (总是生成)
        brief_transcript = smart_truncate_transcript(transcript_text, 800)  # 增加到800字符
        brief_keyframes = "\n".join([
            f"[{kf.timestamp:.1f}s] {kf.description[:100]}..." 
            for kf in keyframe_descriptions[:5]  # 简要总结只用5个关键帧
        ])
        
        brief_prompt = f"""基于以下视频内容，用1-2句话简要总结视频的主要内容：

关键帧描述：
{brief_keyframes}

视频转录文本（完整对话内容）：
{brief_transcript}

请综合视觉内容和语音内容，用简洁的中文回答："""
        
        logger.info(f"简要总结 Prompt 长度: {len(brief_prompt)} 字符")
        brief_summary = await self._call_text_generation(brief_prompt, max_tokens=200)
        logger.info(f"简要总结生成结果: {brief_summary}")
        summaries["brief"] = brief_summary or "视频内容总结生成失败"
        
        # 生成标准总结
        if granularity in ["standard", "detailed"]:
            standard_transcript = smart_truncate_transcript(transcript_text, 2000)  # 增加到2000字符
            
            standard_prompt = f"""基于以下视频内容，生成一个段落级别的标准总结（约100-200字）：

关键帧描述：
{keyframe_texts}

视频完整转录文本（包含所有对话和旁白）：
{standard_transcript}

请综合以下信息生成总结：
1. 视频的主题和目标（从视觉和语音内容中提取）
2. 主要内容要点（结合画面和对话）
3. 关键信息或亮点（重要的视觉场景和语音信息）

请用清晰的中文段落形式回答："""
            
            logger.info(f"标准总结 Prompt 长度: {len(standard_prompt)} 字符")
            standard_summary = await self._call_text_generation(standard_prompt, max_tokens=500)
            summaries["standard"] = standard_summary or summaries["brief"]
        else:
            summaries["standard"] = summaries["brief"]
        
        # 生成详细总结
        if granularity == "detailed":
            # 详细总结使用更多的转录文本
            detailed_transcript = smart_truncate_transcript(transcript_text, 4000)  # 增加到4000字符
            
            detailed_prompt = f"""基于以下视频内容，生成一个详细的分段总结（约300-500字）：

关键帧描述（包含所有关键场景）：
{keyframe_texts}

视频完整转录文本（包含所有对话、旁白和音频信息）：
{detailed_transcript}

请按照以下结构组织总结，充分利用视频的视觉和音频信息：
1. 视频概述（结合画面和开场白）
2. 主要内容分段解析（按时间线结合关键帧和对应的对话内容）
3. 关键信息和要点（重要的视觉元素和核心观点）
4. 总结与结论（基于视频结尾的画面和总结性发言）

请用详细的中文段落形式回答："""
            
            logger.info(f"详细总结 Prompt 长度: {len(detailed_prompt)} 字符")
            detailed_summary = await self._call_text_generation(detailed_prompt, max_tokens=1500)  # 增加到1500
            summaries["detailed"] = detailed_summary or summaries["standard"]
        
        return summaries
    
    async def analyze_frame(
        self,
        image_path: str,
        context: str = "",
        max_retries: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """多模态逐帧理解：把单帧图片喂给 VLM，返回结构化理解。

        返回 {frame_type, is_informative, ocr_text, visual_summary, salient_region}，
        失败/不可用时返回 None。salient_region 为可 zoom in 的归一化区域 [x,y,w,h]。
        """
        if not self.is_available():
            return None

        # 远程 URL 直接用；本地文件用 file:// 让 DashScope 读取
        if image_path.startswith("http://") or image_path.startswith("https://"):
            image_ref = image_path
        else:
            abs_path = os.path.abspath(image_path)
            if not os.path.exists(abs_path):
                return None
            image_ref = f"file://{abs_path}"

        prompt = (
            "你在为视频学习笔记分析一帧画面。严格只输出一个 JSON 对象，字段如下：\n"
            '{"frame_type": "slide|chart|code|talking_head|demo|transition|blank|other", '
            '"is_informative": true 或 false, '
            '"ocr_text": "画面中的文字/数字/代码，没有则空串", '
            '"visual_summary": "一句话描述这帧的关键视觉内容", '
            '"salient_region": [x, y, w, h] 或 null}\n'
            "is_informative=false 表示黑屏、转场、纯人脸无信息等不值得放进笔记的帧。\n"
            "salient_region 是最值得放大查看的关键区域，用 0-1 归一化坐标，无则 null。\n"
            "不要输出 JSON 以外的任何文字。"
        )
        if context:
            prompt += f"\n参考（转录上下文）：{context[:300]}"

        messages = [{"role": "user", "content": [{"image": image_ref}, {"text": prompt}]}]

        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    MultiModalConversation.call,
                    model=self.vision_model,
                    messages=messages,
                    temperature=self.temperature,
                )
                if response and response.status_code == 200:
                    parsed = self._parse_json_object(self._extract_generation_text(response))
                    if parsed:
                        return parsed
                else:
                    logger.warning(
                        f"analyze_frame 返回非200: {getattr(response, 'message', 'no response')}"
                    )
            except Exception as e:
                logger.warning(f"analyze_frame 调用异常(attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
        return None

    @staticmethod
    def _parse_json_object(raw: Optional[str]) -> Optional[Dict[str, Any]]:
        """从模型输出里解析单个 JSON 对象（容忍 ```json 包裹和前后噪声）。"""
        if not raw:
            return None
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        text = match.group(0) if match else raw
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_generation_text(response) -> Optional[str]:
        """兼容两种 DashScope 输出格式：message（qwen3 代）与 text（老模型）。"""
        output = getattr(response, "output", None)
        if output is None:
            return None
        # message 格式：output.choices[0].message.content
        # message / content 可能是 dict 或对象（多模态/纯文本返回结构略有差异），都兼容
        choices = getattr(output, "choices", None)
        if choices:
            first = choices[0]
            message = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
            if isinstance(message, dict):
                content = message.get("content")
            else:
                content = getattr(message, "content", None) if message is not None else None
            if isinstance(content, list):  # 多模态分块返回 [{"text": ...}, ...]
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if content and str(content).strip():
                return str(content).strip()
        # text 格式：output.text
        text = getattr(output, "text", None)
        if text and text.strip():
            return text.strip()
        return None

    async def _call_text_generation(self, prompt: str, max_tokens: int = 500, model: Optional[str] = None) -> Optional[str]:
        """
        调用文本生成 API（纯文本任务）
        
        Args:
            prompt: 提示词
            max_tokens: 最大 token 数
            model: 模型名称（默认使用 qwen-max）
            
        Returns:
            生成的文本
        """
        try:
            # 对于纯文本任务，使用 Generation API 而不是 MultiModalConversation
            # 使用指定模型或默认为 qwen-max
            target_model = model or "qwen-max"
            
            logger.info(f"调用文本生成 API, max_tokens={max_tokens}, model={target_model}")
            
            # 使用 message 输出格式：qwen3 代（qwen3-max / qwen3.7-max 等）只通过
            # output.choices[].message.content 返回；老模型（qwen-max）仍兼容 output.text。
            response = await asyncio.to_thread(
                Generation.call,
                model=target_model,
                prompt=prompt,
                temperature=self.temperature,
                max_tokens=max_tokens,
                result_format="message",
            )

            logger.info(f"API 响应状态: {response.status_code if response else 'None'}")

            if response and response.status_code == 200:
                result = self._extract_generation_text(response)
                if result:
                    logger.info(f"文本生成成功，长度: {len(result)} 字符")
                    logger.info(f"生成内容: {result[:200]}...")  # 只显示前200字符
                    return result

            logger.error(f"文本生成失败: {response.message if response else 'No response'}")
            if response:
                logger.error(f"Response details: {response}")
            return None
            
        except Exception as e:
            logger.exception(f"文本生成异常: {e}")
            return None
    
    async def _generate_timeline_sections(
        self,
        keyframe_descriptions: List[KeyframeDescription],
        transcription: TranscriptMetadata
    ) -> List[SummarySection]:
        """
        生成基于时间线的总结段落
        
        Args:
            keyframe_descriptions: 关键帧描述列表
            transcription: 转录数据
            
        Returns:
            时间线段落列表
        """
        sections = []
        
        if not keyframe_descriptions:
            return sections
        
        # 根据关键帧将视频分段
        # 简单策略：每个关键帧为一个段落的中心点
        for i, kf in enumerate(keyframe_descriptions):
            # 确定段落的时间范围
            start_time = kf.timestamp - 15.0 if i > 0 else 0.0
            end_time = kf.timestamp + 15.0
            
            # 如果有下一个关键帧，则以中点为界
            if i < len(keyframe_descriptions) - 1:
                next_kf = keyframe_descriptions[i + 1]
                end_time = min(end_time, (kf.timestamp + next_kf.timestamp) / 2)
            
            # 获取该时间段的转录文本
            section_text = self._get_context_for_timestamp(
                kf.timestamp, transcription.segments, window=30.0
            )
            
            # 生成段落标题和内容
            title = f"片段 {i+1} ({kf.timestamp:.1f}s)"
            content = f"{kf.description}"
            if section_text:
                content += f"\n\n对话内容：{section_text[:200]}"
            
            section = SummarySection(
                start_time=max(0, start_time),
                end_time=end_time,
                title=title,
                content=content,
                keyframe_ids=[kf.frame_id]
            )
            sections.append(section)
        
        logger.info(f"生成 {len(sections)} 个时间线段落")
        return sections


# 创建单例实例
llm_service = QwenVLService()
