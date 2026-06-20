"""
ExtractFrames 服务：由模型在转录时间轴上挑选关键时间点，再用 ffmpeg 截帧落盘。

设计原则与 transcript 真相源一致：模型只能从已有转录片段的时间范围里挑选时间点，
不会凭空造时间戳；挑选失败/模型不可用时回退到在相关片段上均匀采样。截出的帧锚定在
transcript 时间轴上，可被 artifact 引用、可溯源。
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..core.logging import logger
from ..models.workspace import TranscriptIndexEntry
from .llm_service import llm_service
from .video_service import video_service


class FrameService:
    """模型驱动的关键帧抽取（MVP）。"""

    def _frames_dir(self, video_id: str) -> Path:
        base = Path(settings.STORAGE_DIR) / "frames" / (video_id or "unknown")
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _public_url(self, video_id: str, filename: str) -> str:
        return f"/static/frames/{video_id}/{filename}"

    async def extract_keyframes_with_understanding(
        self,
        video_path: str,
        video_id: str,
        query: str,
        transcript_index: Optional[List[TranscriptIndexEntry]] = None,
        max_frames: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """目标链路：scene detection 抽全部关键帧 → VLM 逐帧看图理解 → 丢无信息帧。

        与盲选(select_and_extract_frames)的本质区别：模型真正"看"了每一帧，
        caption/类型/OCR 都来自像素而非转录猜测。VLM 不可用时返回空（调用方回退盲选）。
        """
        if not settings.WORKSPACE_FRAMES_ENABLED:
            return []
        if not video_path or not Path(video_path).exists():
            return []
        if not llm_service.is_available():
            return []  # 没有 VLM 就走不了"看图"路径，交回调用方回退

        limit = max_frames or settings.MAX_FRAMES_PER_NOTE

        # 1) 视觉关键帧时间点：优先场景检测，退化为均匀采样
        timestamps = await video_service._detect_scenes_with_ffmpeg(video_path)
        if not timestamps:
            timestamps = await video_service._uniform_sampling(
                video_path, max(limit * 2, 8)
            )
        timestamps = sorted(timestamps)[: settings.MAX_KEYFRAME_CANDIDATES]
        if not timestamps:
            return []

        output_dir = self._frames_dir(video_id)
        analyzed: List[Dict[str, Any]] = []
        for order, ts in enumerate(timestamps):
            frame_path = await video_service._extract_frame_at_timestamp(
                video_path, ts, order, output_dir
            )
            if not frame_path:
                continue

            context = self._nearest_transcript_text(ts, transcript_index)
            understanding = await llm_service.analyze_frame(frame_path, context=context)
            if not understanding:
                self._remove_quietly(frame_path)
                continue
            if not understanding.get("is_informative", True):
                # 无信息帧（黑屏/转场/纯人脸）丢弃，不留垃圾文件
                self._remove_quietly(frame_path)
                continue

            filename = Path(frame_path).name
            region = understanding.get("salient_region")
            # zoom in：把关键区域裁剪+放大成独立特写图（图表/代码/幻灯片这类细节帧才值得）
            zoom_url = self._crop_salient_region(
                frame_path, video_id, order, region, understanding.get("frame_type")
            )
            analyzed.append(
                {
                    "timestamp": round(ts, 2),
                    "frame_type": understanding.get("frame_type"),
                    "ocr_text": (understanding.get("ocr_text") or "").strip(),
                    "visual_summary": (understanding.get("visual_summary") or "").strip(),
                    "salient_region": region,
                    # caption 来自像素理解（取代盲选的转录猜测）
                    "reason": (understanding.get("visual_summary") or "").strip(),
                    "frame_url": self._public_url(video_id, filename),
                    "zoom_url": zoom_url,  # 关键区域特写（无则 None）
                }
            )

        logger.info(
            f"AnalyzeFrame 完成: {len(analyzed)} 帧有信息 / {len(timestamps)} 候选 (video_id={video_id})"
        )
        # 已按时间排序；先截断到 limit（后续可按 query 相关性重排）
        return analyzed[:limit]

    @staticmethod
    def _nearest_transcript_text(
        timestamp: float, transcript_index: Optional[List[TranscriptIndexEntry]]
    ) -> str:
        """取该时间点所在/最近的转录片段文本，作为看图的上下文提示。"""
        if not transcript_index:
            return ""
        for seg in transcript_index:
            if seg.start_time <= timestamp <= (seg.end_time or seg.start_time):
                return seg.text
        nearest = min(
            transcript_index,
            key=lambda s: abs(((s.start_time + (s.end_time or s.start_time)) / 2) - timestamp),
        )
        return nearest.text

    # 值得 zoom in 的帧类型（细节密集，特写有价值）
    _ZOOMABLE_TYPES = {"chart", "code", "slide", "demo"}

    def _crop_salient_region(
        self,
        frame_path: str,
        video_id: str,
        order: int,
        region: Optional[List[float]],
        frame_type: Optional[str],
    ) -> Optional[str]:
        """把归一化 salient_region [x,y,w,h] 裁剪出来并放大，存为特写图，返回 url。

        仅对细节型帧(图表/代码/幻灯片/演示)生成特写；区域非法或太小则跳过。
        """
        if not region or frame_type not in self._ZOOMABLE_TYPES:
            return None
        try:
            x, y, w, h = (float(v) for v in region)
        except (TypeError, ValueError):
            return None
        # 归一化区域校验：必须在 [0,1] 且占比不能太小（太小裁出来没意义）
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
            return None
        if w * h < 0.02 or w * h > 0.95:  # 太小或几乎整图，没必要 zoom
            return None

        try:
            from PIL import Image

            with Image.open(frame_path) as img:
                W, H = img.size
                left = int(x * W)
                top = int(y * H)
                right = min(int((x + w) * W), W)
                bottom = min(int((y + h) * H), H)
                if right - left < 10 or bottom - top < 10:
                    return None
                crop = img.crop((left, top, right, bottom))
                # 放大到至少 2 倍，便于看清细节
                scale = max(2, 800 // max(crop.width, 1))
                crop = crop.resize(
                    (crop.width * scale, crop.height * scale), Image.LANCZOS
                )
                zoom_name = f"frame_{order:03d}_zoom.jpg"
                zoom_path = self._frames_dir(video_id) / zoom_name
                crop.convert("RGB").save(str(zoom_path), "JPEG", quality=90)
            return self._public_url(video_id, zoom_name)
        except Exception as e:
            logger.warning(f"zoom 裁剪失败: {e}")
            return None

    @staticmethod
    def _remove_quietly(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    async def select_and_extract_frames(
        self,
        video_path: str,
        video_id: str,
        transcript_index: List[TranscriptIndexEntry],
        query: str,
        max_frames: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """挑选时间点并截帧，返回 frame 引用列表（含 public url + 锚定的 segment）。"""
        if not settings.WORKSPACE_FRAMES_ENABLED:
            logger.info("ExtractFrames 已禁用 (WORKSPACE_FRAMES_ENABLED=false)")
            return []
        if not transcript_index or not video_path or not Path(video_path).exists():
            return []

        limit = max_frames or settings.MAX_FRAMES_PER_NOTE
        selections = await self._select_timestamps(query, transcript_index, limit)
        if not selections:
            return []

        output_dir = self._frames_dir(video_id)
        frames: List[Dict[str, Any]] = []
        for order, (segment, timestamp, reason) in enumerate(selections):
            frame_path = await video_service._extract_frame_at_timestamp(
                video_path, timestamp, order, output_dir
            )
            if not frame_path:
                continue
            filename = Path(frame_path).name
            frames.append(
                {
                    "timestamp": round(timestamp, 2),
                    "segment_index": segment.segment_index,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "text": segment.text,
                    "reason": reason,
                    "frame_url": self._public_url(video_id, filename),
                }
            )

        logger.info(f"ExtractFrames 完成: {len(frames)}/{len(selections)} 帧 (video_id={video_id})")
        return frames

    async def _select_timestamps(
        self,
        query: str,
        transcript_index: List[TranscriptIndexEntry],
        limit: int,
    ) -> List[tuple]:
        """让模型从转录片段中挑选时间点；不可用或解析失败时回退均匀采样。

        返回 [(segment, timestamp, reason), ...]。
        """
        candidates = transcript_index[:60]  # 控制 prompt 体积
        index_by_segment = {seg.segment_index: seg for seg in candidates}

        if llm_service.is_available():
            picked = await self._select_with_llm(query, candidates, limit, index_by_segment)
            if picked:
                return picked
            logger.warning("ExtractFrames 模型选帧失败，回退均匀采样")

        return self._fallback_even_sampling(candidates, limit)

    async def _select_with_llm(
        self,
        query: str,
        candidates: List[TranscriptIndexEntry],
        limit: int,
        index_by_segment: Dict[int, TranscriptIndexEntry],
    ) -> List[tuple]:
        lines = [
            f"#{seg.segment_index} [{seg.start_time:.1f}-{seg.end_time:.1f}s] {seg.text}"
            for seg in candidates
        ]
        prompt = (
            "你在为视频笔记挑选最值得配图的画面。下面是按时间排序的转录片段（含编号与时间范围）。\n"
            f"用户目标：{query.strip() or '（无特定目标，挑选最具代表性的画面）'}\n\n"
            "转录片段：\n" + "\n".join(lines) + "\n\n"
            f"请挑选最多 {limit} 个最值得截图的时刻。规则：\n"
            "1. 只能从上面列出的片段里选；timestamp 必须落在该片段的 start-end 时间范围内。\n"
            "2. 优先选信息密度高、能代表关键内容的画面，避免相邻重复。\n"
            '3. 严格只输出 JSON 数组，每项形如 {"segment_index": 3, "timestamp": 42.5, "reason": "一句话理由"}。\n'
            "不要输出 JSON 以外的任何文字。"
        )

        raw = await llm_service._call_text_generation(
            prompt, max_tokens=600, model=settings.LLM_FRAME_SELECT_MODEL
        )
        if not raw:
            return []

        items = self._parse_json_array(raw)
        if not items:
            return []

        picked: List[tuple] = []
        seen_segments = set()
        for item in items:
            try:
                seg_idx = int(item.get("segment_index"))
            except (TypeError, ValueError):
                continue
            segment = index_by_segment.get(seg_idx)
            if not segment or seg_idx in seen_segments:
                continue
            try:
                ts = float(item.get("timestamp"))
            except (TypeError, ValueError):
                ts = (segment.start_time + segment.end_time) / 2
            # 钳制到片段时间范围内，杜绝模型越界编造时间点
            ts = max(segment.start_time, min(ts, segment.end_time or segment.start_time))
            reason = str(item.get("reason") or "").strip()[:120]
            picked.append((segment, ts, reason))
            seen_segments.add(seg_idx)
            if len(picked) >= limit:
                break
        return picked

    @staticmethod
    def _parse_json_array(raw: str) -> List[Dict[str, Any]]:
        text = raw.strip()
        # 去除可能的 ```json ... ``` 包裹
        fence = re.search(r"\[.*\]", text, re.DOTALL)
        if fence:
            text = fence.group(0)
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _fallback_even_sampling(
        candidates: List[TranscriptIndexEntry], limit: int
    ) -> List[tuple]:
        if not candidates:
            return []
        count = min(limit, len(candidates))
        step = max(len(candidates) // count, 1)
        picked: List[tuple] = []
        for i in range(0, len(candidates), step):
            seg = candidates[i]
            ts = (seg.start_time + seg.end_time) / 2 if seg.end_time else seg.start_time
            picked.append((seg, ts, "均匀采样回退"))
            if len(picked) >= count:
                break
        return picked


frame_service = FrameService()
