"""Centralized, local-only configuration for the VidSnap Harness."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

TOKEN_PLAN_BASE_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
# Token Plan serves text models only, so speech recognition goes to the public DashScope
# native API: `qwen-audio-3.1-asr-flash` is not served in compatible mode (it answers 404
# "Unsupported model ... for OpenAI compatibility mode"). Like the Token Plan URL it is a
# fixed constant: no environment variable, argument, or model output can select a
# different speech endpoint.
DASHSCOPE_ASR_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
# The same public host in OpenAI-compatible mode, used by the evaluation's chat models.
DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen3.8-max"


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Fixed-model provider configuration with a non-printable local credential."""

    api_key: str | None = field(default=None, repr=False)
    model: Literal["qwen3.8-max"] = "qwen3.8-max"
    base_url: str = TOKEN_PLAN_BASE_URL
    model_concurrency: int = 1
    request_timeout_seconds: float = 120.0
    asr_api_key: str | None = field(default=None, repr=False)

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

    @property
    def resolved_asr_api_key(self) -> str | None:
        """The key for the public ASR endpoint: the dedicated ASR key, else the text key."""
        return self.asr_api_key or self.api_key

    @classmethod
    def from_env(cls) -> HarnessConfig:
        """Read only the approved local key names and bounded concurrency setting."""
        api_key = os.getenv("VIDSNAP_QWEN_API_KEY") or os.getenv("QWEN_API_KEY")
        asr_api_key = os.getenv("VIDSNAP_ASR_API_KEY") or None
        raw_concurrency = os.getenv("VIDSNAP_MODEL_CONCURRENCY", "1")
        try:
            requested_concurrency = int(raw_concurrency)
        except ValueError:
            requested_concurrency = 1
        return cls(
            api_key=api_key,
            asr_api_key=asr_api_key,
            model_concurrency=max(1, min(2, requested_concurrency)),
        )
