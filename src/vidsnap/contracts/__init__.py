"""Versioned public contracts for the VidSnap Harness."""

from vidsnap.contracts.agent import AgentDecision, ProviderUsage, ToolCallRequest
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
from vidsnap.contracts.tool_plan import AcquisitionTool, ToolMode, ToolPlan

__all__ = [
    "AcquisitionTool",
    "AgentDecision",
    "Claim",
    "Evidence",
    "EvidenceReference",
    "HarnessPolicy",
    "LoopBudgets",
    "LoopSpec",
    "ProviderUsage",
    "TerminalState",
    "ToolCallRequest",
    "ToolMode",
    "ToolPlan",
    "VideoAnalysisResult",
    "VideoGoal",
    "VideoSource",
    "default_loop_spec",
]
