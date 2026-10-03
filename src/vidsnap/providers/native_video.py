"""Pinned Bailian native audiovisual port over bounded inline Base64 video."""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from vidsnap.contracts.agent import ProviderUsage
from vidsnap.providers.base import ProviderError, ProviderIdentity

NATIVE_VIDEO_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
NATIVE_VIDEO_MODEL = "qwen3.5-omni-plus"
MAX_INLINE_BASE64_BYTES = 10_000_000
MAX_CONTENT_BYTES = 1_000_000
MAX_TOKENS = 4096


@dataclass(frozen=True, slots=True)
class NativeClip:
    """One already prepared, bounded local clip with its true container MIME."""

    path: Path
    mime_type: str
    duration_seconds: float
    sha256: str


class NativeVideoError(ProviderError):
    """Safe failure metadata; never carries raw request or response bodies."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        http_status: int | None = None,
        request_bytes: int = 0,
        attempts: int = 0,
        usage: ProviderUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.http_status = http_status
        self.request_bytes = request_bytes
        self.attempts = attempts
        self.usage = usage


@dataclass(frozen=True, slots=True)
class NativeVideoResult:
    """Text-only notes plus measured usage; absent usage stays unreported."""

    text: str
    usage: ProviderUsage
    identity: ProviderIdentity
    request_bytes: int


class NativeVideoClient:
    """One-shot streaming audiovisual call to the pinned Bailian endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None,
        max_video_bytes: int = 32 * 1024 * 1024,
        base64_max_bytes: int = MAX_INLINE_BASE64_BYTES,
        max_content_bytes: int = MAX_CONTENT_BYTES,
        timeout_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_video_bytes = max_video_bytes
        self._base64_max_bytes = min(base64_max_bytes, MAX_INLINE_BASE64_BYTES)
        self._max_content_bytes = min(max_content_bytes, MAX_CONTENT_BYTES)
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self.identity = ProviderIdentity(
            id="bailian-native-video",
            model=NATIVE_VIDEO_MODEL,
            base_url=NATIVE_VIDEO_BASE_URL,
        )

    async def analyze_clip(self, clip: NativeClip, *, task: str) -> NativeVideoResult:
        """Stream one bounded request; failure is never retried or half-counted."""
        if not self._api_key:
            raise NativeVideoError(
                "No local Bailian key is configured; native video is blocked.",
                category="unavailable",
            )
        video_size = clip.path.stat().st_size
        if video_size > self._max_video_bytes:
            raise NativeVideoError(
                "Clip exceeds the bounded inline video budget.",
                category="oversize",
            )
        video_bytes = clip.path.read_bytes()
        encoded = base64.b64encode(video_bytes).decode("ascii")
        if len(encoded) >= self._base64_max_bytes:
            raise NativeVideoError(
                "Clip exceeds the bounded inline video budget.",
                category="oversize",
            )
        payload = {
            "model": NATIVE_VIDEO_MODEL,
            "modalities": ["text"],
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {
                                "url": f"data:{clip.mime_type};base64,{encoded}",
                            },
                        },
                        {"type": "text", "text": task},
                    ],
                }
            ],
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        text, reported, input_tokens, output_tokens = await self._stream_once(body)
        return NativeVideoResult(
            text=text,
            usage=ProviderUsage(
                model_calls=1,
                input_bytes=len(body),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reported=reported,
            ),
            identity=self.identity,
            request_bytes=len(body),
        )

    async def _stream_once(self, body: bytes) -> tuple[str, bool, int, int]:
        attempts = 1
        observed: dict[str, int] = {}
        async with httpx.AsyncClient(
            base_url=f"{NATIVE_VIDEO_BASE_URL}/",
            transport=self._transport,
            timeout=self._timeout_seconds,
        ) as client:
            try:
                return await asyncio.wait_for(
                    self._stream_within_deadline(client, body, attempts, observed),
                    timeout=self._timeout_seconds,
                )
            except asyncio.TimeoutError:
                raise NativeVideoError(
                    "Native video request exceeded the overall deadline.",
                    category="timeout",
                    request_bytes=len(body),
                    attempts=attempts,
                    usage=_observed_usage(len(body), observed),
                ) from None
            except httpx.HTTPError:
                raise NativeVideoError(
                    "Native video request failed with a network error.",
                    category="network_error",
                    request_bytes=len(body),
                    attempts=attempts,
                    usage=_observed_usage(len(body), observed),
                ) from None

    async def _stream_within_deadline(
        self,
        client: httpx.AsyncClient,
        body: bytes,
        attempts: int,
        observed: dict[str, int],
    ) -> tuple[str, bool, int, int]:
        async with client.stream(
            "POST",
            "chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            content=body,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise NativeVideoError(
                    "Native video request failed with an HTTP error.",
                    category="http_error",
                    http_status=response.status_code,
                    request_bytes=len(body),
                    attempts=attempts,
                )
            return await self._consume_stream(response, len(body), attempts, observed)

    async def _consume_stream(
        self,
        response: httpx.Response,
        request_bytes: int,
        attempts: int,
        observed: dict[str, int],
    ) -> tuple[str, bool, int, int]:
        parts: list[str] = []
        content_bytes = 0
        stopped = False
        done = False
        usage_seen = False
        input_tokens = 0
        output_tokens = 0

        def stream_error() -> NativeVideoError:
            return NativeVideoError(
                "Native video stream did not complete successfully.",
                category="stream_error",
                request_bytes=request_bytes,
                attempts=attempts,
                usage=_observed_usage(request_bytes, observed),
            )

        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                raise stream_error()
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                done = True
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                raise stream_error() from None
            if not isinstance(event, dict):
                raise stream_error()
            if "error" in event:
                raise stream_error()
            usage = event.get("usage")
            if isinstance(usage, dict):
                prompt = _token_count(usage.get("prompt_tokens"))
                completion = _token_count(usage.get("completion_tokens"))
                if prompt is not None and completion is not None:
                    usage_seen = True
                    input_tokens = prompt
                    output_tokens = completion
                    observed["input_tokens"] = prompt
                    observed["output_tokens"] = completion
            for choice in event.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                finish = choice.get("finish_reason")
                if finish == "stop":
                    stopped = True
                elif finish is not None:
                    raise stream_error()
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str):
                        content_bytes += len(content.encode("utf-8"))
                        if content_bytes > self._max_content_bytes:
                            raise NativeVideoError(
                                "Native video response exceeded the bounded text budget.",
                                category="stream_error",
                                request_bytes=request_bytes,
                                attempts=attempts,
                                usage=_observed_usage(request_bytes, observed),
                            )
                        parts.append(content)
        if not done or not stopped:
            raise stream_error()
        text = "".join(parts)
        if not text.strip():
            raise NativeVideoError(
                "Native video stream completed without any text.",
                category="stream_error",
                request_bytes=request_bytes,
                attempts=attempts,
                usage=_observed_usage(request_bytes, observed),
            )
        return text, usage_seen, input_tokens, output_tokens


def _observed_usage(request_bytes: int, observed: dict[str, int]) -> ProviderUsage | None:
    """Safe counters captured before a failure; never fabricates missing values."""
    if "input_tokens" not in observed or "output_tokens" not in observed:
        return None
    return ProviderUsage(
        model_calls=1,
        input_bytes=request_bytes,
        input_tokens=observed["input_tokens"],
        output_tokens=observed["output_tokens"],
        reported=True,
    )


def _token_count(value: object) -> int | None:
    """Strict non-negative token count; bools and anything else stay unknown."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
