"""Adapter projecting the existing video-analysis task onto the kernel contract."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import JsonValue

from vidsnap.contracts import Evidence, VideoAnalysisResult, VideoGoal
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.loop.verifier import verify_claims
from vidsnap.providers.base import VideoModelPort
from vidsnap.tasks.base import TaskVerification
from vidsnap.video.probe import MediaProbe

_KNOWN_GATES = (
    "schema_valid",
    "timestamps_in_bounds",
    "referenced_evidence_exists",
    "claims_are_supported",
    "required_sections_covered",
)


class VideoAnalysisTaskAdapter:
    """Reuse the legacy VideoModelPort and deterministic verifier unchanged."""

    output_model: type[VideoAnalysisResult] = VideoAnalysisResult

    def __init__(self, goal: VideoGoal) -> None:
        self.goal = goal

    async def request_final(
        self,
        model: VideoModelPort,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> tuple[VideoAnalysisResult, ProviderUsage]:
        """Delegate to analyze_evidence and map only reported token counters."""
        del probe
        response = await model.analyze_evidence(evidence, self.goal)
        usage = ProviderUsage(
            model_calls=1,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            reported=response.usage_reported,
        )
        return response.result, usage

    def parse_final(self, payload: dict[str, JsonValue]) -> VideoAnalysisResult:
        """Accept only the strict VideoAnalysisResult schema."""
        return VideoAnalysisResult.model_validate(payload)

    def verify(
        self,
        output: VideoAnalysisResult,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> TaskVerification:
        """Delegate to the deterministic claim verifier with the goal's sections."""
        report = verify_claims(
            claims=output.claims,
            evidence=list(evidence),
            duration_seconds=probe.duration_seconds,
            result=output,
            required_sections=self.goal.required_sections,
        )
        return TaskVerification(
            passed=report.passed,
            gates={gate: gate not in report.failed_gates for gate in _KNOWN_GATES},
            targeted_windows=report.targeted_resample_seconds,
        )
