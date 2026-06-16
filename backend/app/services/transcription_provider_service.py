"""
Transcription provider registry and error classification.
"""
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..core.config import settings


@dataclass(frozen=True)
class TranscriptionProvider:
    name: str
    display_name: str
    available: bool
    retryable_errors: List[str]
    supports_chunking: bool
    supports_local_files: bool
    notes: str = ""


class TranscriptionProviderRegistry:
    """Small adapter boundary for ASR providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, TranscriptionProvider] = {}
        self.refresh()

    def refresh(self) -> None:
        local_enabled = getattr(settings, "LOCAL_ASR_ENABLED", False)
        whisper_available = bool(shutil.which("whisper") or shutil.which("faster-whisper"))

        self._providers = {
            "paraformer": TranscriptionProvider(
                name="paraformer",
                display_name="Aliyun Paraformer",
                available=bool(settings.DASHSCOPE_API_KEY),
                retryable_errors=[
                    "timeout",
                    "connection reset",
                    "unexpected_eof",
                    "eof occurred",
                    "HTTP 408",
                    "HTTP 429",
                    "HTTP 500",
                    "HTTP 502",
                    "HTTP 503",
                    "HTTP 504",
                ],
                supports_chunking=True,
                supports_local_files=False,
                notes="Requires an OSS-accessible audio URL.",
            ),
            "local_asr": TranscriptionProvider(
                name="local_asr",
                display_name="Local ASR",
                available=local_enabled and whisper_available,
                retryable_errors=[],
                supports_chunking=True,
                supports_local_files=True,
                notes="Fallback adapter is defined; install/configure a local ASR runtime to execute it.",
            ),
        }

    def list_providers(self) -> List[TranscriptionProvider]:
        return list(self._providers.values())

    def get(self, name: str) -> Optional[TranscriptionProvider]:
        return self._providers.get(name)

    def default_provider(self) -> TranscriptionProvider:
        return self._providers["paraformer"]

    def classify_error(self, provider_name: str, error: str) -> Dict[str, object]:
        provider = self.get(provider_name) or self.default_provider()
        normalized = (error or "").lower()
        retryable = any(token.lower() in normalized for token in provider.retryable_errors)
        return {
            "provider": provider.name,
            "retryable": retryable,
            "reason": "retryable_provider_error" if retryable else "terminal_provider_error",
        }


transcription_provider_registry = TranscriptionProviderRegistry()
