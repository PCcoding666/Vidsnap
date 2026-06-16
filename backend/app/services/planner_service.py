"""
Deterministic P0 planner for user query -> skill plan.

The planner is intentionally rule-based for P0 so that plan quality can be
evaluated reproducibly against a golden set. LLM planning can be added behind
the same SkillPlan contract later.
"""
import hashlib
import re
from typing import List, Set

from ..models.workspace import ArtifactType, PlanStep, SkillPlan
from .skill_registry_service import skill_registry


class PlannerService:
    """Create structured skill plans from natural language video queries."""

    transcript_terms = {
        "转录",
        "逐字稿",
        "文稿",
        "文字稿",
        "语音文字",
        "讲话内容",
        "字幕",
        "transcript",
        "transcribe",
        "verbatim",
        "caption",
    }
    locate_terms = {
        "定位",
        "找到",
        "查找",
        "搜索",
        "哪里",
        "在哪",
        "时间点",
        "时间范围",
        "时间戳",
        "片段",
        "search",
        "find",
        "locate",
        "timestamp",
        "where",
    }
    notes_terms = {
        "笔记",
        "复习",
        "讲义",
        "提纲",
        "整理",
        "学习",
        "课程",
        "notes",
        "study",
        "outline",
        "handout",
    }
    visual_terms = {
        "图文",
        "截图",
        "图片",
        "画面",
        "界面",
        "视觉",
        "illustrated",
        "screenshot",
        "frame",
        "visual",
        "image",
    }
    qa_terms = {
        "回答",
        "解释",
        "为什么",
        "如何",
        "怎么",
        "是否",
        "问答",
        "answer",
        "explain",
        "why",
        "how",
        "what",
        "?",
        "？",
    }
    summary_terms = {
        "总结",
        "摘要",
        "要点",
        "概括",
        "summary",
        "summarize",
        "recap",
        "takeaway",
        "key points",
    }

    def create_plan(self, query: str) -> SkillPlan:
        normalized_query = self._normalize_query(query)
        artifact_type = self._detect_artifact_type(normalized_query)
        requires_visual = self._contains_any(normalized_query, self.visual_terms)
        cost_tier = "medium" if artifact_type in {"notes", "summary"} or requires_visual else "low"

        steps: List[PlanStep] = [
            PlanStep(
                id="ingest",
                skill="IngestVideo",
                purpose="Create a stable local VideoAsset before any task-specific work.",
                inputs={"source_type": "upload"},
            ),
            PlanStep(
                id="transcribe",
                skill="TranscribeAudio",
                depends_on=["ingest"],
                purpose="Turn the video's speech into timestamped text.",
            ),
            PlanStep(
                id="index",
                skill="BuildTranscriptIndex",
                depends_on=["transcribe"],
                purpose="Make transcript segments searchable and citeable.",
            ),
        ]

        if artifact_type == "summary":
            steps.append(
                PlanStep(
                    id="summarize",
                    skill="SummarizeContent",
                    depends_on=["index"],
                    purpose="Generate a grounded text summary from the transcript.",
                )
            )
        elif artifact_type == "notes":
            dependencies = ["index"]
            if requires_visual:
                steps.append(
                    PlanStep(
                        id="extract_frames",
                        skill="ExtractFrames",
                        depends_on=["index"],
                        purpose="Attach representative frames because the query explicitly asks for visual notes.",
                    )
                )
                dependencies.append("extract_frames")

            steps.append(
                PlanStep(
                    id="summarize",
                    skill="SummarizeContent",
                    depends_on=["index"],
                    purpose="Create the content backbone for notes.",
                )
            )
            dependencies.append("summarize")
            steps.append(
                PlanStep(
                    id="generate_notes",
                    skill="GenerateNotes",
                    depends_on=dependencies,
                    purpose="Produce a reusable note artifact matching the user's request.",
                )
            )
        elif artifact_type == "content_locations":
            steps.append(
                PlanStep(
                    id="locate",
                    skill="LocateContent",
                    depends_on=["index"],
                    purpose="Return relevant transcript time ranges for the requested content.",
                )
            )
        elif artifact_type == "qa_answer":
            steps.append(
                PlanStep(
                    id="answer",
                    skill="AnswerWithContext",
                    depends_on=["index"],
                    purpose="Answer using only the current video's transcript context.",
                )
            )

        assumptions = [
            "The user owns or is allowed to upload the local video.",
            "Transcript text is the source of truth unless the plan explicitly includes ExtractFrames.",
        ]
        rejected = [
            "YouTube downloading is out of scope for Slim.",
            "Cross-video knowledge base search is out of scope for P0.",
        ]

        plan = SkillPlan(
            plan_id=self._plan_id(query),
            query=query.strip(),
            artifact_type=artifact_type,
            steps=steps,
            requires_user_confirmation=requires_visual,
            cost_tier=cost_tier,
            assumptions=assumptions,
            rejected_capabilities=rejected,
        )

        validation = skill_registry.validate_plan(plan)
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))

        return plan

    def _detect_artifact_type(self, normalized_query: str) -> ArtifactType:
        has_transcript = self._contains_any(normalized_query, self.transcript_terms)
        has_locate = self._contains_any(normalized_query, self.locate_terms)
        has_notes = self._contains_any(normalized_query, self.notes_terms)
        has_visual = self._contains_any(normalized_query, self.visual_terms)
        has_qa = self._contains_any(normalized_query, self.qa_terms)
        has_summary = self._contains_any(normalized_query, self.summary_terms)

        transcript_only = (
            "transcript only" in normalized_query
            or "only transcript" in normalized_query
            or "不要总结" in normalized_query
            or "只需要" in normalized_query
            or "只做" in normalized_query
            or "without analysis" in normalized_query
        )

        if has_transcript and (transcript_only or not (has_notes or has_qa or has_summary)):
            return "transcript"
        if has_notes or has_visual:
            return "notes"
        if has_locate:
            return "content_locations"
        if has_summary:
            return "summary"
        if has_qa:
            return "qa_answer"
        return "summary"

    @staticmethod
    def _normalize_query(query: str) -> str:
        return re.sub(r"\s+", " ", query.strip().lower())

    @staticmethod
    def _contains_any(text: str, terms: Set[str]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _plan_id(query: str) -> str:
        digest = hashlib.sha1(query.strip().encode("utf-8")).hexdigest()[:12]
        return f"plan_{digest}"


planner_service = PlannerService()
