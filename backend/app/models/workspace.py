"""
P0 workspace models for query-first video artifacts.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ArtifactType = Literal[
    "transcript",
    "summary",
    "notes",
    "content_locations",
    "qa_answer",
]


class SkillDefinition(BaseModel):
    """Externally visible skill contract."""

    name: str
    description: str
    inputs_schema: Dict[str, Any]
    outputs_schema: Dict[str, Any]
    cost_estimate: Literal["low", "medium", "high"]
    failure_modes: List[str]
    idempotency_key: str
    default_enabled: bool = True


class PlanStep(BaseModel):
    """One executable skill step in a plan."""

    id: str
    skill: str
    depends_on: List[str] = Field(default_factory=list)
    purpose: str
    inputs: Dict[str, Any] = Field(default_factory=dict)


class SkillPlan(BaseModel):
    """Structured planner output."""

    plan_id: str
    query: str
    artifact_type: ArtifactType
    steps: List[PlanStep]
    requires_user_confirmation: bool = False
    cost_tier: Literal["low", "medium", "high"] = "low"
    assumptions: List[str] = Field(default_factory=list)
    rejected_capabilities: List[str] = Field(default_factory=list)


class PlanValidationResult(BaseModel):
    """Planner validation result."""

    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class TranscriptIndexEntry(BaseModel):
    """Searchable transcript segment."""

    segment_index: int
    text: str
    start_time: float
    end_time: float
    confidence: float = 0.0
    chunk_id: Optional[str] = None
    provider: Optional[str] = None


class VideoAsset(BaseModel):
    """Stable video asset created before task-specific artifacts."""

    video_id: str
    title: str
    duration: float
    source_type: Literal["upload"] = "upload"
    processing_status: str
    transcript_segments_count: int = 0
    summary_generated: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    """Task-specific reusable output."""

    artifact_id: str
    artifact_type: ArtifactType
    title: str
    content: str
    format: Literal["markdown", "text", "json"] = "markdown"
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SkillTraceEntry(BaseModel):
    """Execution trace for one skill."""

    step_id: str
    skill: str
    status: Literal["planned", "running", "success", "skipped", "failed"]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    output_summary: Optional[str] = None
    error: Optional[str] = None


class QueryPlanRequest(BaseModel):
    """Request body for plan preview."""

    query: str


class QueryPlanResponse(BaseModel):
    """Plan preview response."""

    status: str
    plan: SkillPlan
    validation: PlanValidationResult


class WorkspaceProcessResponse(BaseModel):
    """End-to-end query-first processing response."""

    status: str
    video_asset: VideoAsset
    plan: SkillPlan
    validation: PlanValidationResult
    artifact: Artifact
    transcript_index: List[TranscriptIndexEntry]
    skill_trace: List[SkillTraceEntry]


JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
JobStage = Literal[
    "uploaded",
    "planning",
    "queued",
    "ingesting",
    "extracting_audio",
    "uploading_audio",
    "transcribing",
    "indexing",
    "generating_artifact",
    "completed",
    "failed",
]


class WorkspaceCostEstimate(BaseModel):
    """Best-effort processing cost and duration estimate."""

    source_file_bytes: int = 0
    source_file_mb: float = 0.0
    source_duration_seconds: Optional[float] = None
    estimated_audio_mb: float = 0.0
    estimated_transcript_minutes: float = 0.0
    provider: str = "paraformer"
    estimated_audio_format: str = "flac"
    chunking_expected: bool = False
    chunk_seconds: int = 0
    estimated_chunks: int = 1
    estimate_source: Literal["media_duration", "file_size_fallback"] = "file_size_fallback"


class ArtifactVersion(BaseModel):
    """Append-only artifact version."""

    version: int
    artifact: Artifact
    query: str
    plan_id: str
    created_at: str


class WorkspaceJobStatus(BaseModel):
    """Persisted in-process job state."""

    job_id: str
    status: JobStatus
    stage: JobStage
    progress: int = Field(ge=0, le=100)
    message: str
    query: str
    original_filename: str
    created_at: str
    updated_at: str
    attempts: int = 0
    max_attempts: int = 3
    retryable: bool = False
    failed_stage: Optional[JobStage] = None
    error: Optional[str] = None
    plan: SkillPlan
    validation: PlanValidationResult
    skill_trace: List[SkillTraceEntry] = Field(default_factory=list)
    cost_estimate: WorkspaceCostEstimate = Field(default_factory=WorkspaceCostEstimate)
    artifact_available: bool = False
    artifact_versions_count: int = 0
    transcript_segments_count: int = 0
    partial: bool = False


class WorkspaceJobCreateResponse(BaseModel):
    """Response returned after a job is accepted."""

    status: str
    job_id: str
    job: WorkspaceJobStatus


class WorkspaceJobArtifactResponse(BaseModel):
    """Latest artifact and reusable job output."""

    status: str
    job_id: str
    video_asset: VideoAsset
    plan: SkillPlan
    validation: PlanValidationResult
    artifact: Artifact
    artifact_versions: List[ArtifactVersion]
    transcript_index: List[TranscriptIndexEntry]
    skill_trace: List[SkillTraceEntry]


class WorkspaceRetryResponse(BaseModel):
    """Retry response."""

    status: str
    job_id: str
    job: WorkspaceJobStatus


class WorkspaceArtifactCreateRequest(BaseModel):
    """Create another artifact version from existing transcript context."""

    query: str
    plan: Optional[SkillPlan] = None


class WorkspaceQARequest(BaseModel):
    """Ask against current transcript context."""

    question: str
    top_k: int = 5


class WorkspaceQAResponse(BaseModel):
    """Transcript-grounded QA result."""

    status: str
    job_id: str
    partial: bool
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
