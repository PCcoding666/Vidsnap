"""Centralized, local-only configuration for the VidSnap Harness."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

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
# The text models and OpenAI-compatible endpoints a run may be configured with. Qwen
# qwen3.8-max on Token Plan stays the default/reference; the others are the
# alternatives the evaluation already allow-lists. Nothing can change these during a run.
APPROVED_QWEN_MODELS: tuple[str, ...] = ("qwen3.8-max", "qwen3.8-flash", "qwen3.8-omni-flash")
ENDPOINT_BASE_URLS: dict[str, str] = {
    "token-plan": TOKEN_PLAN_BASE_URL,
    "dashscope": DASHSCOPE_COMPATIBLE_BASE_URL,
}
APPROVED_BASE_URLS: tuple[str, ...] = tuple(ENDPOINT_BASE_URLS.values())


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Fixed-model provider configuration with a non-printable local credential."""

    api_key: str | None = field(default=None, repr=False)
    model: str = QWEN_MODEL
    base_url: str = TOKEN_PLAN_BASE_URL
    model_concurrency: int = 1
    request_timeout_seconds: float = 120.0
    asr_api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.model not in APPROVED_QWEN_MODELS:
            raise ValueError(f"model must be one of: {', '.join(APPROVED_QWEN_MODELS)}")
        if self.base_url not in APPROVED_BASE_URLS:
            raise ValueError(
                "base_url must be an approved endpoint (Token Plan or public DashScope "
                "compatible mode)"
            )
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
        """Read only the approved local key names, the model and endpoint choice, and
        the bounded concurrency setting.

        ``VIDSNAP_QWEN_MODEL`` picks one of the approved models (default qwen3.8-max) and
        ``VIDSNAP_QWEN_ENDPOINT`` one of ``token-plan`` (default) or ``dashscope``; an
        unknown value raises rather than silently falling back.
        """
        api_key = os.getenv("VIDSNAP_QWEN_API_KEY") or os.getenv("QWEN_API_KEY")
        asr_api_key = os.getenv("VIDSNAP_ASR_API_KEY") or None
        raw_concurrency = os.getenv("VIDSNAP_MODEL_CONCURRENCY", "1")
        try:
            requested_concurrency = int(raw_concurrency)
        except ValueError:
            requested_concurrency = 1
        model = os.getenv("VIDSNAP_QWEN_MODEL") or QWEN_MODEL
        endpoint = os.getenv("VIDSNAP_QWEN_ENDPOINT") or "token-plan"
        if endpoint not in ENDPOINT_BASE_URLS:
            raise ValueError(
                "VIDSNAP_QWEN_ENDPOINT must be one of: " + ", ".join(ENDPOINT_BASE_URLS)
            )
        return cls(
            api_key=api_key,
            asr_api_key=asr_api_key,
            model=model,
            base_url=ENDPOINT_BASE_URLS[endpoint],
            model_concurrency=max(1, min(2, requested_concurrency)),
        )
