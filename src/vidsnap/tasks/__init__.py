"""Task adapters that bind one analysis task to the unified harness kernel."""

from vidsnap.tasks.base import ModelT, OutputT, TaskAdapter, TaskVerification
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter

__all__ = [
    "ModelT",
    "OutputT",
    "TaskAdapter",
    "TaskVerification",
    "VideoAnalysisTaskAdapter",
]
