"""Versioned public contracts for the VidSnap Harness."""

from vidsnap.contracts.loopspec import LoopBudgets, LoopSpec, default_loop_spec
from vidsnap.contracts.models import (
    Claim,
    Evidence,
    EvidenceReference,
    HarnessPolicy,
    TerminalState,
    VideoAnalysisResult,
    VideoGoal,
    VideoSource,
)

__all__ = [
    "Claim",
    "Evidence",
    "EvidenceReference",
    "HarnessPolicy",
    "LoopBudgets",
    "LoopSpec",
    "TerminalState",
    "VideoAnalysisResult",
    "VideoGoal",
    "VideoSource",
    "default_loop_spec",
]
