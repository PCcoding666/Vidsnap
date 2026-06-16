"""
Skill registry for the VidSnap query-first workspace.
"""
from typing import Dict, Iterable, List, Set

from ..models.workspace import PlanValidationResult, SkillDefinition, SkillPlan


class SkillRegistryService:
    """Registry and validator for externally visible P0 skills."""

    def __init__(self) -> None:
        self._skills: Dict[str, SkillDefinition] = {}
        self._register_default_skills()

    def _register_default_skills(self) -> None:
        self.register(
            SkillDefinition(
                name="IngestVideo",
                description="Validate a local video upload and create a stable VideoAsset.",
                inputs_schema={"video_file": "multipart file"},
                outputs_schema={"video_asset": "VideoAsset"},
                cost_estimate="low",
                failure_modes=[
                    "missing_file",
                    "unsupported_format",
                    "metadata_probe_failed",
                    "temporary_file_cleanup_failed",
                ],
                idempotency_key="video_file_sha256",
            )
        )
        self.register(
            SkillDefinition(
                name="TranscribeAudio",
                description="Extract audio from the video and produce timestamped transcript segments.",
                inputs_schema={"video_asset": "VideoAsset"},
                outputs_schema={"transcript": "TranscriptMetadata"},
                cost_estimate="medium",
                failure_modes=[
                    "no_audio_track",
                    "speech_service_unavailable",
                    "transcription_empty",
                ],
                idempotency_key="video_id:transcript:v1",
            )
        )
        self.register(
            SkillDefinition(
                name="BuildTranscriptIndex",
                description="Build searchable transcript segments for locating and citing video content.",
                inputs_schema={"transcript": "TranscriptMetadata"},
                outputs_schema={"transcript_index": "TranscriptIndexEntry[]"},
                cost_estimate="low",
                failure_modes=["empty_transcript", "index_build_failed"],
                idempotency_key="video_id:transcript_index:v1",
            )
        )
        self.register(
            SkillDefinition(
                name="SummarizeContent",
                description="Generate a grounded text summary from transcript content and video metadata.",
                inputs_schema={"transcript": "TranscriptMetadata", "video_asset": "VideoAsset"},
                outputs_schema={"summary": "markdown"},
                cost_estimate="medium",
                failure_modes=["llm_unavailable", "empty_transcript", "summary_generation_failed"],
                idempotency_key="video_id:summary:v1",
            )
        )
        self.register(
            SkillDefinition(
                name="LocateContent",
                description="Find transcript time ranges relevant to the user's query.",
                inputs_schema={"query": "string", "transcript_index": "TranscriptIndexEntry[]"},
                outputs_schema={"locations": "time_range[]"},
                cost_estimate="low",
                failure_modes=["empty_index", "no_relevant_segment_found"],
                idempotency_key="video_id:query_hash:locations:v1",
            )
        )
        self.register(
            SkillDefinition(
                name="GenerateNotes",
                description="Create structured notes or study material from transcript, summary, and citations.",
                inputs_schema={"query": "string", "summary": "markdown", "locations": "time_range[]"},
                outputs_schema={"notes": "markdown"},
                cost_estimate="medium",
                failure_modes=["missing_summary", "notes_generation_failed"],
                idempotency_key="video_id:query_hash:notes:v1",
            )
        )
        self.register(
            SkillDefinition(
                name="AnswerWithContext",
                description="Answer a user question using only the current video's transcript context.",
                inputs_schema={"query": "string", "transcript_index": "TranscriptIndexEntry[]"},
                outputs_schema={"answer": "markdown", "citations": "time_range[]"},
                cost_estimate="low",
                failure_modes=["empty_context", "answer_not_supported_by_context"],
                idempotency_key="video_id:query_hash:qa:v1",
            )
        )
        self.register(
            SkillDefinition(
                name="ExtractFrames",
                description="Optionally extract representative frames only when the user explicitly asks for visual notes or screenshots.",
                inputs_schema={"video_asset": "VideoAsset", "locations": "time_range[]"},
                outputs_schema={"frames": "frame_reference[]"},
                cost_estimate="medium",
                failure_modes=["frame_extraction_disabled", "ffmpeg_failed", "no_relevant_frame"],
                idempotency_key="video_id:query_hash:frames:v1",
                default_enabled=False,
            )
        )

    def register(self, skill: SkillDefinition) -> None:
        self._skills[skill.name] = skill

    def list_skills(self) -> List[SkillDefinition]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillDefinition:
        return self._skills[name]

    def has_skill(self, name: str) -> bool:
        return name in self._skills

    def validate_plan(self, plan: SkillPlan) -> PlanValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        step_ids: Set[str] = set()

        for step in plan.steps:
            if step.id in step_ids:
                errors.append(f"duplicate step id: {step.id}")
            step_ids.add(step.id)

            if not self.has_skill(step.skill):
                errors.append(f"unknown skill: {step.skill}")

        for step in plan.steps:
            for dependency in step.depends_on:
                if dependency not in step_ids:
                    errors.append(f"step {step.id} depends on missing step {dependency}")

        cycle_errors = self._detect_cycles(plan)
        errors.extend(cycle_errors)

        if plan.artifact_type == "notes" and not self._plan_has_skill(plan, "GenerateNotes"):
            errors.append("notes artifacts require GenerateNotes")
        if plan.artifact_type == "content_locations" and not self._plan_has_skill(plan, "LocateContent"):
            errors.append("content_locations artifacts require LocateContent")
        if plan.artifact_type == "qa_answer" and not self._plan_has_skill(plan, "AnswerWithContext"):
            errors.append("qa_answer artifacts require AnswerWithContext")

        if self._plan_has_skill(plan, "ExtractFrames") and plan.artifact_type != "notes":
            warnings.append("ExtractFrames should only be used for visual note artifacts in P0")

        return PlanValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def _detect_cycles(self, plan: SkillPlan) -> List[str]:
        dependencies = {step.id: set(step.depends_on) for step in plan.steps}
        visiting: Set[str] = set()
        visited: Set[str] = set()
        errors: List[str] = []

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                errors.append(f"cycle detected at step {step_id}")
                return

            visiting.add(step_id)
            for dependency in dependencies.get(step_id, set()):
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in dependencies:
            visit(step_id)
        return errors

    @staticmethod
    def _plan_has_skill(plan: SkillPlan, skill_name: str) -> bool:
        return any(step.skill == skill_name for step in plan.steps)


skill_registry = SkillRegistryService()
