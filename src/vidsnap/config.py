"""Centralized, local-only configuration for the VidSnap Harness."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

TOKEN_PLAN_BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen3.8-max"


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Fixed-model provider configuration with a non-printable local credential."""

    api_key: str | None = field(default=None, repr=False)
    model: Literal["qwen3.8-max"] = QWEN_MODEL
    base_url: str = TOKEN_PLAN_BASE_URL
    model_concurrency: int = 1
    request_timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.model != QWEN_MODEL:
            raise ValueError(f"model must be {QWEN_MODEL}")
        if self.base_url != TOKEN_PLAN_BASE_URL:
            raise ValueError("base_url must be the approved Token Plan endpoint")
        if self.model_concurrency < 1:
            raise ValueError("model_concurrency must be positive")
        object.__setattr__(self, "model_concurrency", min(2, self.model_concurrency))
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

    @classmethod
    def from_env(cls) -> HarnessConfig:
        """Read only the approved local key names and bounded concurrency setting."""
        api_key = os.getenv("VIDSNAP_QWEN_API_KEY") or os.getenv("QWEN_API_KEY")
        raw_concurrency = os.getenv("VIDSNAP_MODEL_CONCURRENCY", "1")
        try:
            requested_concurrency = int(raw_concurrency)
        except ValueError:
            requested_concurrency = 1
        return cls(api_key=api_key, model_concurrency=max(1, min(2, requested_concurrency)))
