"""
Query-first workspace execution service.
"""
from dataclasses import asdict, is_dataclass
from datetime import datetime
import hashlib
import re
import time
from typing import Any, Dict, List, Optional

from ..core.logging import logger
from ..models.workspace import (
    Artifact,
    SkillTraceEntry,
    TranscriptIndexEntry,
    VideoAsset,
    WorkspaceProcessResponse,
)
from .frame_service import frame_service
from .pipeline_service import pipeline
from .planner_service import planner_service
from .skill_registry_service import skill_registry


class WorkspaceProcessingError(RuntimeError):
    """Processing error with a machine-readable pipeline failure stage."""

    def __init__(self, message: str, failure_stage: Optional[str] = None) -> None:
        super().__init__(message)
        self.failure_stage = failure_stage


class WorkspaceService:
    """Execute a query-first skill plan against an uploaded local video."""

    async def process_video_query(
        self,
        video_file_path: str,
        original_filename: str,
        query: str,
        user_id: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        plan=None,
    ) -> WorkspaceProcessResponse:
        # 允许调用方传入预建 plan（含用户手动补充的工具），否则按 query 重新规划。
        plan = plan or planner_service.create_plan(query)
        validation = skill_registry.validate_plan(plan)
        trace = self._initial_trace(plan.steps)

        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        self._mark_running(trace, "ingest")
        start = time.time()
        result = await pipeline.process_video_with_summary(
            video_file=video_file_path,
            user_id=user_id,
            progress_callback=progress_callback,
        )
        self._mark_done(trace, "ingest", start, "Local upload accepted and video asset created")

        if result.get("status") != "success":
            error = result.get("error", "video processing failed")
            self._mark_failed(trace, "transcribe", error)
            raise WorkspaceProcessingError(
                error,
                failure_stage=result.get("failure_stage") or self._infer_failure_stage(error),
            )

        metadata = self._to_dict(result.get("metadata") or {})
        summary = self._to_dict(result.get("video_summary") or {})
        video_asset = self._build_video_asset(result, metadata, summary, original_filename)

        transcript_start = time.time()
        self._mark_running(trace, "transcribe")
        transcript_segments = self._extract_transcript_segments(metadata)
        if transcript_segments:
            self._mark_done(
                trace,
                "transcribe",
                transcript_start,
                f"{len(transcript_segments)} transcript segments available",
            )
        else:
            self._mark_failed(trace, "transcribe", "No transcript segments were produced")

        index_start = time.time()
        self._mark_running(trace, "index")
        transcript_index = self._build_transcript_index(transcript_segments)
        if transcript_index:
            self._mark_done(trace, "index", index_start, f"{len(transcript_index)} searchable segments")
        else:
            self._mark_failed(trace, "index", "Transcript index is empty")

        artifact = await self._create_artifact(
            plan=plan,
            video_asset=video_asset,
            transcript_index=transcript_index,
            summary=summary,
            query=query,
            trace=trace,
            video_file_path=video_file_path,
        )

        return WorkspaceProcessResponse(
            status="success",
            video_asset=video_asset,
            plan=plan,
            validation=validation,
            artifact=artifact,
            transcript_index=transcript_index,
            skill_trace=trace,
        )

    async def create_artifact_from_existing(
        self,
        response: WorkspaceProcessResponse,
        query: str,
        plan=None,
    ) -> WorkspaceProcessResponse:
        plan = plan or planner_service.create_plan(query)
        validation = skill_registry.validate_plan(plan)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        trace = self._initial_trace(plan.steps)
        artifact = await self._create_artifact(
            plan=plan,
            video_asset=response.video_asset,
            transcript_index=response.transcript_index,
            summary={},
            query=query,
            trace=trace,
        )

        return WorkspaceProcessResponse(
            status="success",
            video_asset=response.video_asset,
            plan=plan,
            validation=validation,
            artifact=artifact,
            transcript_index=response.transcript_index,
            skill_trace=trace,
        )

    async def _create_artifact(
        self,
        plan,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
        summary: Dict[str, Any],
        query: str,
        trace: List[SkillTraceEntry],
        video_file_path: Optional[str] = None,
    ) -> Artifact:
        if plan.artifact_type == "transcript":
            return self._create_transcript_artifact(video_asset, transcript_index)
        if plan.artifact_type == "content_locations":
            return self._create_locations_artifact(video_asset, transcript_index, query, trace)
        if plan.artifact_type == "notes":
            return await self._create_notes_artifact(
                video_asset, transcript_index, summary, query, trace, plan, video_file_path
            )
        if plan.artifact_type == "qa_answer":
            return self._create_qa_artifact(video_asset, transcript_index, query, trace)
        return self._create_summary_artifact(video_asset, transcript_index, summary, trace)

    def _create_transcript_artifact(
        self,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
    ) -> Artifact:
        content = "\n".join(
            f"[{self._format_range(seg.start_time, seg.end_time)}] {seg.text}"
            for seg in transcript_index
        )
        if not content:
            content = "No transcript content is available. The system will not fabricate video text."

        return Artifact(
            artifact_id=self._artifact_id(video_asset.video_id, "transcript", "transcript"),
            artifact_type="transcript",
            title=f"{video_asset.title} - Transcript",
            content=content,
            format="text",
            citations=self._citations_from_segments(transcript_index[:10]),
        )

    def _create_summary_artifact(
        self,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
        summary: Dict[str, Any],
        trace: List[SkillTraceEntry],
    ) -> Artifact:
        self._mark_running(trace, "summarize")
        start = time.time()
        content = self._summary_text(summary)
        if not content:
            content = self._fallback_summary(video_asset, transcript_index)
        self._mark_done(trace, "summarize", start, "Summary artifact generated")

        return Artifact(
            artifact_id=self._artifact_id(video_asset.video_id, "summary", "summary"),
            artifact_type="summary",
            title=f"{video_asset.title} - Summary",
            content=content,
            citations=self._citations_from_segments(transcript_index[:5]),
        )

    async def _create_notes_artifact(
        self,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
        summary: Dict[str, Any],
        query: str,
        trace: List[SkillTraceEntry],
        plan,
        video_file_path: Optional[str] = None,
    ) -> Artifact:
        summary_artifact = self._create_summary_artifact(video_asset, transcript_index, summary, trace)

        frame_step = next((step for step in plan.steps if step.skill == "ExtractFrames"), None)
        visual_note = ""
        frames: List[Dict[str, Any]] = []
        if frame_step:
            frames, visual_note = await self._extract_frames_for_notes(
                frame_step.id, video_asset, transcript_index, query, trace, video_file_path
            )

        self._mark_running(trace, "generate_notes")
        start = time.time()
        top_segments = transcript_index[:6]
        section_lines = []
        for idx, segment in enumerate(top_segments, 1):
            section_lines.append(
                f"{idx}. **{self._format_time(segment.start_time)}** - {segment.text}"
            )

        content = (
            f"# {video_asset.title}\n\n"
            f"## User Goal\n{query.strip()}\n\n"
            f"## Condensed Understanding\n{summary_artifact.content}\n\n"
            "## Timestamped Notes\n"
            + ("\n".join(section_lines) if section_lines else "No transcript-backed notes are available.")
            + visual_note
            + "\n\n## Source Boundary\n"
            "This note is grounded in the video's transcript. It does not claim visual details unless frame extraction is explicitly available."
        )
        self._mark_done(trace, "generate_notes", start, "Markdown notes generated")

        return Artifact(
            artifact_id=self._artifact_id(video_asset.video_id, "notes", query),
            artifact_type="notes",
            title=f"{video_asset.title} - Notes",
            content=content,
            citations=self._citations_from_segments(top_segments),
            metadata={"frames": frames} if frames else {},
        )

    async def _extract_frames_for_notes(
        self,
        step_id: str,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
        query: str,
        trace: List[SkillTraceEntry],
        video_file_path: Optional[str],
    ) -> tuple:
        """执行 ExtractFrames：模型在转录时间轴上选点截帧，返回 (frames, markdown 片段)。"""
        # 再版本化等场景下原始视频已被清理，无法截帧，优雅降级。
        if not video_file_path:
            self._mark_skipped(
                trace,
                step_id,
                "Original video is no longer available (input cleaned up); no frames were extracted or fabricated.",
            )
            return [], (
                "\n\n## Visual References\n"
                "Frames were requested but the original video is no longer available for this version. "
                "No screenshot has been fabricated.\n"
            )

        self._mark_running(trace, step_id)
        start = time.time()
        try:
            # 首选"看图"路径：scene detection 抽帧 + VLM 逐帧理解
            frames = await frame_service.extract_keyframes_with_understanding(
                video_path=video_file_path,
                video_id=video_asset.video_id,
                query=query,
                transcript_index=transcript_index,
            )
            # VLM 不可用或无产出时回退到盲选（转录驱动）
            if not frames:
                frames = await frame_service.select_and_extract_frames(
                    video_path=video_file_path,
                    video_id=video_asset.video_id,
                    transcript_index=transcript_index,
                    query=query,
                )
        except Exception as e:  # 截帧失败不应让整个笔记任务挂掉
            logger.warning(f"ExtractFrames 失败: {e}")
            self._mark_failed(trace, step_id, f"frame extraction failed: {e}")
            return [], (
                "\n\n## Visual References\n"
                "Frame extraction was attempted but failed; no screenshot has been fabricated.\n"
            )

        if not frames:
            self._mark_done(trace, step_id, start, "No frames selected")
            return [], ""

        self._mark_done(trace, step_id, start, f"{len(frames)} frames extracted")
        lines = ["\n\n## Visual References"]
        for frame in frames:
            ts = self._format_time(frame["timestamp"])
            caption = frame.get("reason") or frame.get("text", "")
            lines.append(f"\n![{ts}]({frame['frame_url']})")
            lines.append(f"*[{ts}] {caption}*")
            # zoom in 特写图（关键区域放大）
            if frame.get("zoom_url"):
                lines.append(f"\n🔍 ![{ts} 特写]({frame['zoom_url']})")
            # OCR：画面文字入笔记（转录里没有的信息）
            ocr = (frame.get("ocr_text") or "").strip()
            if ocr:
                lines.append(f"> 📃 画面文字：{ocr}")
        return frames, "\n".join(lines) + "\n"

    def _create_locations_artifact(
        self,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
        query: str,
        trace: List[SkillTraceEntry],
    ) -> Artifact:
        self._mark_running(trace, "locate")
        start = time.time()
        locations = self._find_locations(query, transcript_index)
        self._mark_done(trace, "locate", start, f"{len(locations)} locations returned")

        if locations:
            content = "\n".join(
                f"- [{self._format_range(seg.start_time, seg.end_time)}] {seg.text}"
                for seg in locations
            )
        else:
            content = "No transcript segment confidently matched the requested content."

        return Artifact(
            artifact_id=self._artifact_id(video_asset.video_id, "content_locations", query),
            artifact_type="content_locations",
            title=f"{video_asset.title} - Located Content",
            content=content,
            citations=self._citations_from_segments(locations),
        )

    def _create_qa_artifact(
        self,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
        query: str,
        trace: List[SkillTraceEntry],
    ) -> Artifact:
        self._mark_running(trace, "answer")
        start = time.time()
        locations = self._find_locations(query, transcript_index)
        if locations:
            evidence = "\n".join(
                f"- [{self._format_range(seg.start_time, seg.end_time)}] {seg.text}"
                for seg in locations[:3]
            )
            content = (
                "I can answer only from the current video's transcript context.\n\n"
                f"**Answer basis:**\n{evidence}"
            )
        else:
            content = (
                "I do not have enough transcript context to answer this reliably. "
                "No unsupported answer was generated."
            )
        self._mark_done(trace, "answer", start, "Transcript-grounded answer generated")

        return Artifact(
            artifact_id=self._artifact_id(video_asset.video_id, "qa_answer", query),
            artifact_type="qa_answer",
            title=f"{video_asset.title} - Answer",
            content=content,
            citations=self._citations_from_segments(locations[:3]),
        )

    def _build_video_asset(
        self,
        result: Dict[str, Any],
        metadata: Dict[str, Any],
        summary: Dict[str, Any],
        original_filename: str,
    ) -> VideoAsset:
        transcript_segments = self._extract_transcript_segments(metadata)
        return VideoAsset(
            video_id=result.get("video_id") or metadata.get("video_id") or "",
            title=metadata.get("title") or original_filename,
            duration=float(metadata.get("duration") or 0),
            source_type="upload",
            processing_status=metadata.get("processing_status") or "completed",
            transcript_segments_count=len(transcript_segments),
            summary_generated=bool(self._summary_text(summary)),
            metadata=metadata,
        )

    def _extract_transcript_segments(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        transcript = metadata.get("transcript") or {}
        if is_dataclass(transcript):
            transcript = asdict(transcript)
        segments = transcript.get("segments") if isinstance(transcript, dict) else []
        output: List[Dict[str, Any]] = []
        for segment in segments or []:
            segment_dict = self._to_dict(segment)
            text = str(segment_dict.get("text") or "").strip()
            if text:
                output.append(
                    {
                        "text": text,
                        "start_time": float(segment_dict.get("start_time") or 0.0),
                        "end_time": float(segment_dict.get("end_time") or 0.0),
                        "confidence": float(segment_dict.get("confidence") or 0.0),
                        "chunk_id": segment_dict.get("chunk_id"),
                        "provider": segment_dict.get("provider"),
                    }
                )
        return output

    def _build_transcript_index(self, segments: List[Dict[str, Any]]) -> List[TranscriptIndexEntry]:
        return [
            TranscriptIndexEntry(
                segment_index=index,
                text=segment["text"],
                start_time=segment["start_time"],
                end_time=segment["end_time"],
                confidence=segment["confidence"],
                chunk_id=segment.get("chunk_id"),
                provider=segment.get("provider"),
            )
            for index, segment in enumerate(segments)
        ]

    def _find_locations(
        self,
        query: str,
        transcript_index: List[TranscriptIndexEntry],
        limit: int = 5,
    ) -> List[TranscriptIndexEntry]:
        if not transcript_index:
            return []

        query_tokens = self._query_tokens(query)
        scored = []
        for segment in transcript_index:
            segment_text = segment.text.lower()
            token_score = sum(2 for token in query_tokens if token and token in segment_text)
            char_score = len(set(query.lower()) & set(segment_text)) / max(len(set(query.lower())), 1)
            score = token_score + char_score
            if score > 0.2:
                scored.append((score, segment))

        scored.sort(key=lambda item: (-item[0], item[1].start_time))
        return [segment for _, segment in scored[:limit]]

    def _query_tokens(self, query: str) -> List[str]:
        lower = query.lower()
        latin_tokens = re.findall(r"[a-z0-9][a-z0-9_\-]{1,}", lower)
        cjk_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", lower)
        stop_words = {
            "找到",
            "定位",
            "哪里",
            "在哪",
            "提到",
            "内容",
            "视频",
            "片段",
            "时间",
            "时间点",
            "帮我",
        }
        tokens = latin_tokens + cjk_tokens
        return [token for token in tokens if token not in stop_words]

    def _fallback_summary(
        self,
        video_asset: VideoAsset,
        transcript_index: List[TranscriptIndexEntry],
    ) -> str:
        if not transcript_index:
            return (
                "No transcript-backed summary is available. "
                "The system will not fabricate video content."
            )
        preview = " ".join(segment.text for segment in transcript_index[:5])
        return f"{video_asset.title} appears to cover the following transcript content: {preview}"

    def _summary_text(self, summary: Dict[str, Any]) -> str:
        if not summary:
            return ""
        for key in ("detailed_summary", "detailed", "standard", "brief"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _citations_from_segments(self, segments: List[TranscriptIndexEntry]) -> List[Dict[str, Any]]:
        return [
            {
                "segment_index": segment.segment_index,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text,
            }
            for segment in segments
        ]

    def _initial_trace(self, steps) -> List[SkillTraceEntry]:
        return [
            SkillTraceEntry(step_id=step.id, skill=step.skill, status="planned")
            for step in steps
        ]

    def _mark_running(self, trace: List[SkillTraceEntry], step_id: str) -> None:
        entry = self._trace_entry(trace, step_id)
        if entry:
            entry.status = "running"
            entry.started_at = datetime.now().isoformat()

    def _mark_done(
        self,
        trace: List[SkillTraceEntry],
        step_id: str,
        start: float,
        summary: str,
    ) -> None:
        entry = self._trace_entry(trace, step_id)
        if entry:
            entry.status = "success"
            entry.completed_at = datetime.now().isoformat()
            entry.duration_ms = round((time.time() - start) * 1000, 2)
            entry.output_summary = summary

    def _mark_failed(self, trace: List[SkillTraceEntry], step_id: str, error: str) -> None:
        entry = self._trace_entry(trace, step_id)
        if entry:
            entry.status = "failed"
            entry.completed_at = datetime.now().isoformat()
            entry.error = error

    def _mark_skipped(self, trace: List[SkillTraceEntry], step_id: str, reason: str) -> None:
        entry = self._trace_entry(trace, step_id)
        if entry:
            entry.status = "skipped"
            entry.completed_at = datetime.now().isoformat()
            entry.output_summary = reason

    @staticmethod
    def _trace_entry(trace: List[SkillTraceEntry], step_id: str) -> Optional[SkillTraceEntry]:
        return next((entry for entry in trace if entry.step_id == step_id), None)

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes = int(seconds // 60)
        remaining = int(seconds % 60)
        return f"{minutes:02d}:{remaining:02d}"

    def _format_range(self, start: float, end: float) -> str:
        return f"{self._format_time(start)}-{self._format_time(end)}"

    @staticmethod
    def _artifact_id(video_id: str, artifact_type: str, seed: str) -> str:
        digest = hashlib.sha1(f"{video_id}:{artifact_type}:{seed}".encode("utf-8")).hexdigest()[:12]
        return f"artifact_{digest}"

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return value
        if hasattr(value, "dict"):
            return value.dict()
        return {}

    @staticmethod
    def _infer_failure_stage(error: str) -> str:
        normalized = (error or "").lower()
        if any(token in normalized for token in ("oss", "上传")):
            return "uploading_audio"
        if any(token in normalized for token in ("transcrib", "transcript", "transcription", "asr", "paraformer", "dashscope", "转录")):
            return "transcribing"
        if any(token in normalized for token in ("ffmpeg", "extract", "音频提取")):
            return "extracting_audio"
        return "failed"


workspace_service = WorkspaceService()
