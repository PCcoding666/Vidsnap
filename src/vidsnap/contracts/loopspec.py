"""Versioned contract for the bounded video-understanding loop."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from vidsnap.contracts.models import StrictModel, TerminalState

SkillName = Literal[
    "probe_media",
    "transcribe_audio",
    "sample_evidence",
    "inspect_evidence",
    "synthesize_result",
    "verify_claims",
]


class LoopBudgets(StrictModel):
    """Absolute resource caps enforced by the loop controller."""

    max_iterations: int = Field(default=3, ge=1, le=3)
    max_model_calls: int = Field(default=12, ge=0, le=12)
    max_evidence_frames: int = Field(default=96, ge=1, le=96)
    max_wall_seconds: int = Field(default=900, ge=1, le=900)


class LoopSpec(StrictModel):
    """The machine-readable specification of the approved harness surface."""

    api_version: Literal["vidsnap.loop/v1"] = "vidsnap.loop/v1"
    id: Literal["grounded-video-understanding"] = "grounded-video-understanding"
    allowed_skills: tuple[SkillName, ...] = (
        "probe_media",
        "transcribe_audio",
        "sample_evidence",
        "inspect_evidence",
        "synthesize_result",
        "verify_claims",
    )
    budgets: LoopBudgets = Field(default_factory=LoopBudgets)
    verification_gates: tuple[str, ...] = (
        "schema_valid",
        "referenced_evidence_exists",
        "timestamps_in_bounds",
        "claims_supported",
        "required_sections_non_empty",
    )
    terminal_states: tuple[TerminalState, ...] = (
        TerminalState.SUCCEEDED,
        TerminalState.PARTIAL,
        TerminalState.NO_OP,
        TerminalState.BLOCKED,
        TerminalState.EXHAUSTED,
        TerminalState.FAILED,
        TerminalState.CANCELLED,
    )
    max_repair_rounds: int = Field(default=2, ge=0, le=2)

    def digest(self) -> str:
        """Return the stable hash used to bind runs and prompt assets to this spec."""
        canonical_json = json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def default_loop_spec() -> LoopSpec:
    """Create a fresh instance of the approved version-one LoopSpec."""
    return LoopSpec()
