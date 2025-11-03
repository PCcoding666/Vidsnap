"""
视频多轮对话服务
支持基于视频元数据（转录文本+关键帧）的智能问答
使用 Qwen3-VL-Plus 进行多模态对话
"""
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..core.logging import logger
from ..models.analysis import (
    TranscriptMetadata,
    TranscriptSegment,
    KeyframeMetadata,
)
from .llm_service import llm_service
from .supabase_service import supabase_service
from dashscope import MultiModalConversation


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    keyframe_ids: List[int] = field(default_factory=list)
    segment_indices: List[int] = field(default_factory=list)
    time_ranges: List[Dict[str, float]] = field(default_factory=list)


@dataclass
class ChatSession:
    """聊天会话"""
    session_id: str
    video_id: str
    transcript: TranscriptMetadata
    keyframes: List[KeyframeMetadata]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    history: List[ChatMessage] = field(default_factory=list)
    # 新增：缓存视频元数据与AI总结，确保VL模型访问完整上下文
    video_meta: Dict[str, Any] = field(default_factory=dict)
    summaries: Dict[str, str] = field(default_factory=dict)


class VideoChatService:
    """视频聊天服务（v0.2.0 增强：支持 Agent 路由）"""
    
    def __init__(self):
        """初始化聊天服务"""
        self.sessions: Dict[str, ChatSession] = {}
        self.llm_service = llm_service
        logger.info("视频聊天服务初始化完成（支持 Agent 路由）")
    
    def _dict_to_transcript_metadata(self, data: Dict[str, Any]) -> TranscriptMetadata:
        """将字典转换为 TranscriptMetadata"""
        segments = []
        for s in (data.get("segments") or []):
            seg = TranscriptSegment(
                text=s.get("text", ""),
                start_time=float(s.get("start_time", 0.0)),
                end_time=float(s.get("end_time", 0.0)),
                confidence=float(s.get("confidence", 0.0)),
            )
            segments.append(seg)
        
        return TranscriptMetadata(
            oss_audio_url=data.get("oss_audio_url", ""),
            language=data.get("language", "zh-CN"),
            overall_confidence=float(data.get("overall_confidence", 0.0)),
            segments=segments,
        )
    
    def _dict_to_keyframes(self, arr: List[Dict[str, Any]]) -> List[KeyframeMetadata]:
        """将字典列表转换为 KeyframeMetadata 列表"""
        keyframes = []
        for i, k in enumerate(arr or []):
            kf = KeyframeMetadata(
                frame_id=int(k.get("frame_id", i)),
                timestamp=float(k.get("timestamp", 0.0)),
                oss_image_url=k.get("oss_image_url", ""),
                scene_description=k.get("scene_description", ""),
            )
            keyframes.append(kf)
        return keyframes
    
    def start_session(
        self,
        video_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        启动新的聊天会话
        支持两种模式：
        1. 直接传入 metadata（兼容旧用法）
        2. 仅传入 video_id 时，自动从 Supabase 汇聚完整上下文（关键帧+转录+元数据+AI总结）
        
        Args:
            video_id: 视频 ID
            metadata: 视频元数据（可选，包含 transcript 和 keyframes）
            
        Returns:
            包含 session_id 的响应
        """
        if not self.llm_service.is_available():
            return {
                "status": "error",
                "error": "LLM 服务不可用，请检查 QWEN_API_KEY 配置"
            }
        
        try:
            # 记录输入参数用于调试
            logger.info(f"[DEBUG] start_session: video_id={video_id}, metadata={'provided' if metadata else 'None'}")
            
            # 若未提供 metadata 或 metadata 为空，自动从 Supabase 编译完整上下文
            compiled = None
            # 检查metadata是否为空或没有有效内容
            has_valid_metadata = (
                metadata and 
                (metadata.get("transcript") or metadata.get("keyframes"))
            )
            
            if not has_valid_metadata:
                if supabase_service.is_available():
                    logger.info(f"从 Supabase 自动加载视频上下文: {video_id}")
                    compiled = supabase_service.get_compiled_metadata(video_id)
                    if not compiled:
                        logger.warning(f"未能从 Supabase 获取上下文: {video_id}，使用空上下文")
                        compiled = {"transcript": {"segments": []}, "keyframes": [], "video": {}, "summaries": {}}
                    else:
                        logger.info(f"[DEBUG] 编译成功: keyframes={len(compiled.get('keyframes', []))}, segments={len(compiled.get('transcript', {}).get('segments', []))}")
                else:
                    logger.warning("Supabase 服务不可用，无法自动加载上下文")
                    compiled = {"transcript": {"segments": []}, "keyframes": [], "video": {}, "summaries": {}}
                metadata = {"transcript": compiled.get("transcript"), "keyframes": compiled.get("keyframes")}
            else:
                logger.info(f"[DEBUG] 使用传入的metadata")
            
            # 解析 metadata
            transcript = self._dict_to_transcript_metadata(
                metadata.get("transcript", {}) or {} if metadata else {}
            )
            keyframes = self._dict_to_keyframes(
                metadata.get("keyframes", []) or [] if metadata else []
            )
            
            logger.info(f"[DEBUG] 解析后: transcript_segments={len(transcript.segments)}, keyframes={len(keyframes)}")
            
            # 生成会话 ID
            session_id = str(uuid.uuid4())
            
            # 创建会话，附加视频元数据与AI总结以确保上下文完整性
            self.sessions[session_id] = ChatSession(
                session_id=session_id,
                video_id=video_id,
                transcript=transcript,
                keyframes=keyframes,
                video_meta=(compiled or {}).get("video", {}),
                summaries=(compiled or {}).get("summaries", {})
            )
            
            logger.info(
                f"聊天会话创建成功: {session_id} "
                f"(video_id={video_id}, "
                f"keyframes={len(keyframes)}, "
                f"transcript_segments={len(transcript.segments)})"
            )
            
            return {
                "status": "success",
                "session_id": session_id,
                "video_id": video_id,
                "keyframes_count": len(keyframes),
                "transcript_segments_count": len(transcript.segments)
            }
            
        except Exception as e:
            logger.exception(f"创建聊天会话失败: {e}")
            return {
                "status": "error",
                "error": f"创建会话失败: {str(e)}"
            }
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """获取聊天会话"""
        return self.sessions.get(session_id)
    
    def end_session(self, session_id: str) -> bool:
        """结束聊天会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"聊天会话已结束: {session_id}")
            return True
        return False
    
    def _classify_question_type(self, question: str) -> str:
        """
        分类问题类型（v0.2.0 Agent 路由框架）
        
        Args:
            question: 用户问题
            
        Returns:
            问题类型: "visual" | "ocr" | "audio" | "reasoning" | "text"
        """
        question_lower = question.lower()
        
        # 视觉类问题
        visual_keywords = ["画面", "图片", "看到", "显示", "出现", "场景", "visual", "image", "picture"]
        if any(kw in question_lower for kw in visual_keywords):
            return "visual"
        
        # OCR 文字识别类
        ocr_keywords = ["文字", "字幕", "标题", "ocr", "text in", "读出"]
        if any(kw in question_lower for kw in ocr_keywords):
            return "ocr"
        
        # 音频分析类
        audio_keywords = ["情绪", "语气", "声音", "语调", "emotion", "tone", "voice"]
        if any(kw in question_lower for kw in audio_keywords):
            return "audio"
        
        # 推理类
        reasoning_keywords = ["为什么", "原因", "怎么", "如何", "why", "how", "reason", "explain"]
        if any(kw in question_lower for kw in reasoning_keywords):
            return "reasoning"
        
        # 默认为文本类
        return "text"
    
    def _route_to_model(self, question_type: str, question: str) -> Dict[str, Any]:
        """
        根据问题类型路由到最佳模型（v0.2.0 Agent 路由框架）
        
        Args:
            question_type: 问题类型
            question: 用户问题
            
        Returns:
            路由策略: {"model": str, "requires_keyframes": bool, "requires_audio": bool}
        """
        # 视觉类：使用 Qwen3-VL-Flash
        if question_type == "visual":
            return {
                "model": self.llm_service.vision_model,  # qwen-vl-max
                "requires_keyframes": True,
                "requires_audio": False,
                "strategy": "visual_analysis"
            }
        
        # OCR 类：未来可使用 tongyi-qwen-vl-ocr
        if question_type == "ocr":
            return {
                "model": self.llm_service.vision_model,
                "requires_keyframes": True,
                "requires_audio": False,
                "strategy": "ocr_extraction"
            }
        
        # 音频类：未来可使用 qwen-audio
        if question_type == "audio":
            return {
                "model": self.llm_service.text_model,
                "requires_keyframes": False,
                "requires_audio": True,
                "strategy": "audio_analysis"
            }
        
        # 推理类：使用多模态模型
        if question_type == "reasoning":
            return {
                "model": self.llm_service.vision_model,  # qwen-vl-max
                "requires_keyframes": True,
                "requires_audio": False,
                "strategy": "complex_reasoning"
            }
        
        # 文本类：使用多模态模型 qwen-vl-plus，支持文本+关键帧多模态分析
        return {
            "model": self.llm_service.text_model,  # qwen-vl-plus (多模态模型)
            "requires_keyframes": True,  # 强制启用关键帧以支持多模态分析
            "requires_audio": False,
            "strategy": "multimodal_text_qa"
        }
    
    def _get_full_transcript_text(
        self,
        transcript: TranscriptMetadata,
    ) -> Dict[str, Any]:
        """
        获取完整的转录文本内容
        
        Args:
            transcript: 转录元数据
            
        Returns:
            包含完整转录文本和所有片段时间范围的字典
        """
        if not transcript or not transcript.segments:
            return {
                "context_text": "",
                "segment_indices": [],
                "time_ranges": []
            }
        
        # 组合完整的转录文本
        context_text = " ".join(seg.text for seg in transcript.segments)
        
        # 获取所有片段索引
        segment_indices = list(range(len(transcript.segments)))
        
        # 提取所有时间范围
        time_ranges = [
            {
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "text": seg.text[:100]  # 只保留前100字符作为预览
            }
            for seg in transcript.segments
        ]
        
        logger.info(f"获取完整转录文本，总长度: {len(context_text)} 字符，片段数: {len(transcript.segments)}")
        
        return {
            "context_text": context_text,
            "segment_indices": segment_indices,
            "time_ranges": time_ranges
        }
    
    def _find_relevant_keyframes(
        self,
        time_ranges: List[Dict[str, float]],
        keyframes: List[KeyframeMetadata],
        max_keyframes: int = 3
    ) -> List[KeyframeMetadata]:
        """
        根据时间范围查找相关的关键帧
        
        Args:
            time_ranges: 时间范围列表
            keyframes: 所有关键帧
            max_keyframes: 最大返回数量
            
        Returns:
            相关的关键帧列表
        """
        if not time_ranges or not keyframes:
            return []
        
        relevant_kfs = []
        for kf in keyframes:
            for tr in time_ranges:
                if tr["start_time"] <= kf.timestamp <= tr["end_time"]:
                    relevant_kfs.append(kf)
                    break
        
        # 限制数量
        return relevant_kfs[:max_keyframes]
    
    async def ask_question(
        self,
        session_id: str,
        question: str,
        keyframe_ids: Optional[List[int]] = None,
        top_k: int = 5,
        max_length: int = 800,
        auto_keyframes: bool = True
    ) -> Dict[str, Any]:
        """
        在会话中提问
        
        Args:
            session_id: 会话 ID
            question: 用户问题
            keyframe_ids: 指定的关键帧 ID（用于视觉问答）
            top_k: 检索的相关片段数量
            max_length: LLM 最大输出长度
            auto_keyframes: 是否自动查找相关关键帧
            
        Returns:
            包含答案和引用信息的响应
        """
        # 获取会话
        session = self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": "无效的 session_id，会话不存在或已过期"
            }
        
        if not self.llm_service.is_available():
            return {
                "status": "error",
                "error": "LLM 服务不可用"
            }
        
        try:
            # 步骤 0: Agent 路由（v0.2.0 新增）
            question_type = self._classify_question_type(question)
            routing_strategy = self._route_to_model(question_type, question)
            
            logger.info(f"Agent 路由: 问题类型={question_type}, 策略={routing_strategy['strategy']}, 模型={routing_strategy['model']}")
            
            # 步骤 1: 获取完整的转录文本
            logger.info(f"获取完整转录文本用于问答: {question[:50]}...")
            logger.info(f"[DEBUG] session.transcript: segments={len(session.transcript.segments) if session.transcript and session.transcript.segments else 0}")
            retrieval = self._get_full_transcript_text(session.transcript)
            logger.info(f"[DEBUG] retrieval: context_text_length={len(retrieval['context_text'])}, segments={len(retrieval['segment_indices'])}")
            logger.info(f"[DEBUG] context_text preview: {retrieval['context_text'][:200]}...")
            
            # 步骤 2: 准备关键帧（根据路由策略决定是否需要）
            used_keyframes: List[KeyframeMetadata] = []
            
            # 仅当路由策略要求时才获取关键帧
            if routing_strategy["requires_keyframes"]:
                # 用户指定的关键帧
                if keyframe_ids:
                    for kfid in keyframe_ids:
                        kf = next(
                            (k for k in session.keyframes if k.frame_id == kfid),
                            None
                        )
                        if kf and kf.oss_image_url:
                            used_keyframes.append(kf)
                
                # 自动查找相关关键帧
                elif auto_keyframes and retrieval["time_ranges"]:
                    # 根据问题类型调整关键帧数量
                    max_kf = 5 if question_type in ["visual", "ocr"] else 3
                    auto_kfs = self._find_relevant_keyframes(
                        retrieval["time_ranges"],
                        session.keyframes,
                        max_keyframes=max_kf
                    )
                    used_keyframes.extend(auto_kfs)
            
            logger.info(f"使用关键帧数量: {len(used_keyframes)}, 问题类型={question_type}, 需要关键帧={routing_strategy['requires_keyframes']}")
            
            # 步骤 3: 构建多模态消息（传递关键帧URL + 视频元数据 + AI总结）
            content_parts: List[Dict[str, Any]] = []
            
            # 添加用户问题
            content_parts.append({"text": f"用户问题：{question}"})
            
            # 添加完整转录文本
            if retrieval["context_text"]:
                content_parts.append({
                    "text": f"\n完整视频转录文本：\n{retrieval['context_text']}"
                })
            
            # 添加关键帧图像（如果路由策略要求）
            if routing_strategy["requires_keyframes"] and used_keyframes:
                content_parts.append({"text": "\n相关关键帧："})
                for kf in used_keyframes:
                    if kf.oss_image_url:
                        content_parts.append({"image": kf.oss_image_url})
                        if kf.scene_description:
                            content_parts.append({
                                "text": f"关键帧 {kf.frame_id} ({kf.timestamp:.1f}s): {kf.scene_description}"
                            })
            
            # 添加视频元数据（标题、时长、来源）
            if session.video_meta:
                title = session.video_meta.get("title") or ""
                duration = session.video_meta.get("duration") or 0.0
                source = session.video_meta.get("source_type") or ""
                if title or duration or source:
                    content_parts.append({
                        "text": f"\n视频元信息：标题《{title}》 | 时长 {duration:.1f} 秒 | 来源 {source}"
                    })
            
            # 添加已生成的 AI 总结（若有）
            if session.summaries:
                brief = session.summaries.get("brief")
                standard = session.summaries.get("standard")
                detailed = session.summaries.get("detailed")
                if brief:
                    content_parts.append({"text": f"\n已有AI简要总结：{brief}"})
                if standard:
                    content_parts.append({"text": f"\n已有AI标准总结：{standard}"})
                if detailed:
                    # 详细总结可能较长，限制传入长度避免超长上下文
                    preview = detailed[:1200] + ("..." if len(detailed) > 1200 else "")
                    content_parts.append({"text": f"\n已有AI详细总结(截断)：{preview}"})
            
            # 步骤 4: 构建完整的对话历史
            system_prompt = (
                "你是一个专业的视频助理,能够结合视频的完整转录文本和关键帧图像来回答用户问题。\n\n"
                "重要说明:\n"
                "- 你已经获得了视频的完整转录文本,无需担心信息缺失\n"
                "- 你可以对整个视频内容进行全面分析和回答\n\n"
                "回答要求:\n"
                "1. 仅基于提供的完整转录文本进行回答,不要编造或猜测信息\n"
                "2. 对于事实性问题,请完整列出转录文本中的所有相关信息\n"
                "3. 如果问题涉及时间定位,请分析整个转录文本,找出所有相关位置并给出时间范围\n"
                "4. 如果问题涉及视觉内容,请结合关键帧图像进行描述\n"
                "5. 回答要简洁、准确、完整,使用中文\n"
                "6. 可以对视频内容进行总结、归纳、对比等分析\n"
                "7. 如果转录文本中确实未提及相关信息,请明确说明\n"
            )
            
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": [{"text": system_prompt}]}
            ]
            
            # 添加历史对话（保留最近 4 轮）
            for msg in session.history[-8:]:  # 8条=4轮对话
                messages.append({
                    "role": msg.role,
                    "content": [{"text": msg.content}]
                })
            
            # 添加当前问题
            messages.append({
                "role": "user",
                "content": content_parts
            })
            
            # 步骤 5: 调用 Qwen3-VL-Plus 进行对话
            logger.info(f"调用 LLM 生成回答，使用模型: {self.llm_service.text_model}")
            
            # [DEBUG] 打印完整的messages结构
            logger.info(f"[DEBUG] ========== 发送给LLM的完整消息 ==========")
            logger.info(f"[DEBUG] 总消息数: {len(messages)}")
            for idx, msg in enumerate(messages):
                logger.info(f"[DEBUG] Message[{idx}]: role={msg['role']}")
                content = msg.get('content', [])
                if isinstance(content, list):
                    logger.info(f"[DEBUG]   - Content parts: {len(content)} 个")
                    for cidx, part in enumerate(content):
                        if 'text' in part:
                            text_preview = part['text'][:300] if len(part['text']) > 300 else part['text']
                            logger.info(f"[DEBUG]   - Part[{cidx}] TEXT ({len(part['text'])} 字符): {text_preview}...")
                        elif 'image' in part:
                            logger.info(f"[DEBUG]   - Part[{cidx}] IMAGE: {part['image']}")
                else:
                    logger.info(f"[DEBUG]   - Content: {str(content)[:200]}")
            logger.info(f"[DEBUG] ===========================================")
            
            response = await asyncio.to_thread(
                MultiModalConversation.call,
                model=self.llm_service.text_model,  # qwen-vl-plus
                messages=messages,
                temperature=self.llm_service.temperature,
                max_length=max_length
            )
            
            # 步骤 6: 处理响应
            if not response or response.status_code != 200:
                error_msg = response.message if response else "No response"
                logger.error(f"LLM 调用失败: {error_msg}")
                return {
                    "status": "error",
                    "error": f"模型调用失败: {error_msg}"
                }
            
            # 提取答案文本
            content = response.output.choices[0].message.content
            if isinstance(content, list):
                answer_text = content[0].get("text", "") if content else ""
            elif isinstance(content, str):
                answer_text = content
            else:
                logger.error(f"未知的响应格式: {type(content)}")
                return {
                    "status": "error",
                    "error": "响应格式异常"
                }
            
            logger.info(f"LLM 回答生成成功，长度: {len(answer_text)} 字符")
            
            # 步骤 7: 保存对话历史
            user_msg = ChatMessage(
                role="user",
                content=question,
                keyframe_ids=[kf.frame_id for kf in used_keyframes],
                segment_indices=retrieval["segment_indices"],
                time_ranges=retrieval["time_ranges"]
            )
            
            assistant_msg = ChatMessage(
                role="assistant",
                content=answer_text
            )
            
            session.history.append(user_msg)
            session.history.append(assistant_msg)
            
            # 步骤 8: 返回结果
            return {
                "status": "success",
                "session_id": session_id,
                "answer": answer_text,
                "references": {
                    "time_ranges": retrieval["time_ranges"],
                    "keyframe_ids": [kf.frame_id for kf in used_keyframes],
                    "keyframes": [
                        {
                            "frame_id": kf.frame_id,
                            "timestamp": kf.timestamp,
                            "oss_image_url": kf.oss_image_url
                        }
                        for kf in used_keyframes
                    ]
                },
                "history_length": len(session.history)
            }
            
        except Exception as e:
            logger.exception(f"问答处理失败: {e}")
            return {
                "status": "error",
                "error": f"问答失败: {str(e)}"
            }
    
    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话信息
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话信息
        """
        session = self.get_session(session_id)
        if not session:
            return {
                "status": "error",
                "error": "会话不存在"
            }
        
        # 获取最近的对话
        recent_messages = []
        for msg in session.history[-10:]:
            recent_messages.append({
                "role": msg.role,
                "content": msg.content[:200] if len(msg.content) > 200 else msg.content,
                "timestamp": msg.timestamp
            })
        
        return {
            "status": "success",
            "session_id": session_id,
            "video_id": session.video_id,
            "created_at": session.created_at,
            "history_length": len(session.history),
            "recent_messages": recent_messages,
            "keyframes_count": len(session.keyframes),
            "transcript_segments_count": len(session.transcript.segments)
        }
    
    def list_sessions(self) -> Dict[str, Any]:
        """列出所有活动会话"""
        sessions_info = []
        for session_id, session in self.sessions.items():
            sessions_info.append({
                "session_id": session_id,
                "video_id": session.video_id,
                "created_at": session.created_at,
                "history_length": len(session.history)
            })
        
        return {
            "status": "success",
            "sessions": sessions_info,
            "total": len(sessions_info)
        }


# 创建单例实例
video_chat_service = VideoChatService()
