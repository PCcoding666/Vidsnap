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


class VideoChatService:
    """视频聊天服务"""
    
    def __init__(self):
        """初始化聊天服务"""
        self.sessions: Dict[str, ChatSession] = {}
        self.llm_service = llm_service
        logger.info("视频聊天服务初始化完成")
    
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
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        启动新的聊天会话
        
        Args:
            video_id: 视频 ID
            metadata: 视频元数据（包含 transcript 和 keyframes）
            
        Returns:
            包含 session_id 的响应
        """
        if not self.llm_service.is_available():
            return {
                "status": "error",
                "error": "LLM 服务不可用，请检查 QWEN_API_KEY 配置"
            }
        
        try:
            # 解析 metadata
            transcript = self._dict_to_transcript_metadata(
                metadata.get("transcript", {})
            )
            keyframes = self._dict_to_keyframes(
                metadata.get("keyframes", [])
            )
            
            # 生成会话 ID
            session_id = str(uuid.uuid4())
            
            # 创建会话
            self.sessions[session_id] = ChatSession(
                session_id=session_id,
                video_id=video_id,
                transcript=transcript,
                keyframes=keyframes,
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
    
    def _smart_truncate(self, text: str, max_length: int) -> str:
        """
        智能截断文本，保留开头和结尾
        
        Args:
            text: 原始文本
            max_length: 最大长度
            
        Returns:
            截断后的文本
        """
        if len(text) <= max_length:
            return text
        
        # 保留开头 60% 和结尾 40%
        head_length = int(max_length * 0.6)
        tail_length = int(max_length * 0.4)
        
        return text[:head_length] + "\n...(中间部分省略)...\n" + text[-tail_length:]
    
    def _retrieve_relevant_context(
        self,
        question: str,
        transcript: TranscriptMetadata,
        top_k: int = 10,  # 增加到 10 个片段
    ) -> Dict[str, Any]:
        """
        从转录文本中检索与问题相关的上下文
        
        Args:
            question: 用户问题
            transcript: 转录元数据
            top_k: 返回最相关的 K 个片段
            
        Returns:
            包含上下文文本、片段索引和时间范围的字典
        """
        if not transcript or not transcript.segments:
            return {
                "context_text": "",
                "segment_indices": [],
                "time_ranges": []
            }
        
        # 改进：使用多种匹配策略
        question_lower = question.lower()
        
        # 1. 提取关键词（忽略常用词）
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", 
                      "的", "了", "吗", "吗", "呢", "吧", "吗", "怎么", "什么", "哪些", "怎样"}
        question_tokens = set(q.lower() for q in question.split() if len(q) > 1 and q.lower() not in stop_words)
        
        # 2. 计算每个片段的相关性得分
        scored_segments = []
        for i, seg in enumerate(transcript.segments):
            text_lower = seg.text.lower()
            
            # 策略 1: 关键词匹配（基础分）
            keyword_score = sum(1 for token in question_tokens if token in text_lower)
            
            # 策略 2: 完整短语匹配（高分）
            # 提取 2-3 个词的短语
            question_words = [w for w in question.split() if len(w) > 1]
            phrase_score = 0
            for j in range(len(question_words) - 1):
                phrase = " ".join(question_words[j:j+2]).lower()
                if phrase in text_lower:
                    phrase_score += 3  # 短语匹配权重更高
                if j < len(question_words) - 2:
                    phrase3 = " ".join(question_words[j:j+3]).lower()
                    if phrase3 in text_lower:
                        phrase_score += 5  # 3词短语权重最高
            
            # 策略 3: 全文包含（极高分）
            substring_score = 10 if question_lower in text_lower else 0
            
            # 总分
            total_score = keyword_score + phrase_score + substring_score
            
            if total_score > 0:
                scored_segments.append((total_score, i, seg))
        
        # 如果没有匹配，返回开头的几个片段
        if not scored_segments:
            logger.warning(f"未找到相关片段，返回开头 {top_k} 个片段")
            indices = list(range(min(top_k, len(transcript.segments))))
            selected_segments = [transcript.segments[i] for i in indices]
        else:
            # 按得分排序，取前 top_k 个
            scored_segments.sort(key=lambda x: (-x[0], x[1]))
            logger.info(f"找到 {len(scored_segments)} 个相关片段，最高得分: {scored_segments[0][0]}")
            
            indices = [i for _, i, _ in scored_segments[:top_k]]
            indices.sort()  # 按时间顺序排序
            selected_segments = [transcript.segments[i] for i in indices]
        
        # 组合上下文文本
        context_text = " ".join(seg.text for seg in selected_segments)
        
        # 截断过长的文本（保留更多上下文）
        max_context_length = 3000  # 增加到 3000 字符
        context_text = self._smart_truncate(context_text, max_context_length)
        
        # 提取时间范围
        time_ranges = [
            {
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "text": seg.text[:100]  # 只保留前100字符作为预览
            }
            for seg in selected_segments
        ]
        
        logger.info(f"检索到 {len(selected_segments)} 个相关片段，总长度: {len(context_text)} 字符")
        
        return {
            "context_text": context_text,
            "segment_indices": indices,
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
            # 步骤 1: 检索相关的转录上下文
            logger.info(f"检索问题相关上下文: {question[:50]}...")
            retrieval = self._retrieve_relevant_context(
                question, session.transcript, top_k=top_k
            )
            
            # 步骤 2: 准备关键帧
            used_keyframes: List[KeyframeMetadata] = []
            
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
                auto_kfs = self._find_relevant_keyframes(
                    retrieval["time_ranges"],
                    session.keyframes,
                    max_keyframes=2  # 自动时最多2个
                )
                used_keyframes.extend(auto_kfs)
            
            logger.info(f"使用关键帧数量: {len(used_keyframes)}")
            
            # 步骤 3: 构建多模态消息
            content_parts: List[Dict[str, Any]] = []
            
            # 添加问题
            content_parts.append({"text": f"用户问题：{question}"})
            
            # 添加转录上下文
            if retrieval["context_text"]:
                content_parts.append({
                    "text": f"\n相关转录文本（用于定位视频时间段）：\n{retrieval['context_text']}"
                })
            
            # 添加关键帧图像
            for kf in used_keyframes:
                if kf.oss_image_url:
                    content_parts.append({"image": kf.oss_image_url})
                    if kf.scene_description:
                        content_parts.append({
                            "text": f"关键帧 {kf.frame_id} ({kf.timestamp:.1f}s): {kf.scene_description}"
                        })
            
            # 步骤 4: 构建完整的对话历史
            system_prompt = (
                "你是一个专业的视频助理，能够结合视频的转录文本和关键帧图像来回答用户问题。\n\n"
                "回答要求：\n"
                "1. **仅基于提供的转录文本进行回答**，不要编造或猜测信息\n"
                "2. 对于事实性问题（如“支持哪些编辑器”），请直接引用转录文本中的原文\n"
                "3. 如果问题涉及时间定位（如“在哪里讲了XXX”），请给出具体的时间范围（格式：MM:SS或HH:MM:SS）\n"
                "4. 如果问题涉及视觉内容，请结合关键帧图像进行描述\n"
                "5. 回答要简洁、准确、完整，使用中文\n"
                "6. **如果转录文本中有明确的答案，请完整列出所有相关项**\n"
                "7. 如果信息不足以回答问题，请说明“转录文本中未提及该信息”"
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
