"""Allow-listed Bailian clients for evaluation: synthesis, native video and ASR.

Models, endpoints and key variables are fixed here; a system picks one entry
before a run and never switches during it. Keys come only from environment
variables and are never logged or written to traces. Failures carry only the
allow-listed ``vidsnap.provider-failure/v1`` record.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import JsonValue

from vidsnap.config import TOKEN_PLAN_BASE_URL
from vidsnap.contracts import Evidence
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.failures import ProviderFailure
from vidsnap.eval.suite import EvalItem
from vidsnap.eval.tasks import EvalTask
from vidsnap.plugins.base import TranscriptionResponse
from vidsnap.providers.asr import QWEN_ASR_MODEL, Base64AudioChunker
from vidsnap.providers.base import ProviderError, ProviderIdentity, ProviderUnavailable
from vidsnap.providers.failures import http_failure, request_body_bytes
from vidsnap.video.probe import MediaProbe

EndpointName = Literal["dashscope", "token-plan"]

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MOCK_BASE_URL = "offline://mock"
NATIVE_BASE64_LIMIT = 10_000_000
_BASE64_HEADROOM = 0.95
_MIN_TRANSCODE_VIDEO_KBPS = 40
_AUDIO_KBPS = 32


@dataclass(frozen=True, slots=True)
class Endpoint:
    name: EndpointName
    base_url: str
    key_variables: tuple[str, ...]


ENDPOINTS: dict[EndpointName, Endpoint] = {
    "dashscope": Endpoint(
        "dashscope", DASHSCOPE_BASE_URL, ("VIDSNAP_DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY")
    ),
    "token-plan": Endpoint(
        "token-plan", TOKEN_PLAN_BASE_URL, ("VIDSNAP_QWEN_API_KEY", "QWEN_API_KEY")
    ),
}


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """How one allow-listed model is called."""

    model: str
    endpoints: tuple[EndpointName, ...]
    stream: bool
    json_mode: bool
    omni: bool = False


HARNESS_MODELS: dict[str, ModelProfile] = {
    "qwen3.8-max": ModelProfile("qwen3.8-max", ("dashscope", "token-plan"), False, True),
    "qwen3.8-flash": ModelProfile("qwen3.8-flash", ("dashscope", "token-plan"), False, True),
    "qwen3.8-omni-flash": ModelProfile("qwen3.8-omni-flash", ("dashscope",), True, False, True),
}
NATIVE_MODELS: dict[str, ModelProfile] = {
    "qwen3.8-omni-flash": ModelProfile("qwen3.8-omni-flash", ("dashscope",), True, False, True),
    "qwen3.5-omni-plus": ModelProfile("qwen3.5-omni-plus", ("dashscope",), True, False, True),
    "qwen3.8-max": ModelProfile("qwen3.8-max", ("dashscope", "token-plan"), False, False),
}
ASR_ENDPOINTS: tuple[EndpointName, ...] = ("dashscope",)


def endpoint_key(endpoint: EndpointName) -> str | None:
    """Read the endpoint's key from the environment; never log or return it elsewhere."""
    for variable in ENDPOINTS[endpoint].key_variables:
        value = os.environ.get(variable)
        if value:
            return value
    return None


@dataclass(frozen=True, slots=True)
class Completion:
    """One parsed model reply: the JSON object, usage and modality details."""

    payload: dict[str, Any]
    usage: ProviderUsage
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """Everything one harness synthesis call needs; mocks read only the typed parts."""

    task: EvalTask[Any]
    item: EvalItem
    system_prompt: str
    content: list[dict[str, object]]
    evidence: Sequence[Evidence]
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class NativeRequest:
    """One native-video call: the whole local video plus the task prompt."""

    task: EvalTask[Any]
    item: EvalItem
    prompt: str
    video: Path
    probe: MediaProbe
    work_dir: Path


class SynthesisPort(Protocol):
    identity: ProviderIdentity

    async def synthesize(self, request: SynthesisRequest) -> Completion:
        """Return the task JSON for typed evidence."""


class NativeVideoPort(Protocol):
    identity: ProviderIdentity

    async def analyze_video(self, request: NativeRequest) -> Completion:
        """Return the task JSON for the whole video."""


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object, tolerating Markdown fences and leading or trailing prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    candidates = [stripped]
    start, end = stripped.find("{"), stripped.rfind("}")
    if 0 <= start < end:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _counter(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def usage_details(usage: Mapping[str, Any]) -> dict[str, JsonValue]:
    """Per-modality counters, renamed so trace redaction keeps them."""
    details: dict[str, JsonValue] = {}
    prompt = usage.get("prompt_tokens_details")
    if isinstance(prompt, dict):
        for source, target in (
            ("audio_tokens", "input_audio"),
            ("video_tokens", "input_video"),
            ("image_tokens", "input_image"),
            ("text_tokens", "input_text"),
            ("cached_tokens", "input_cached"),
        ):
            value = _counter(prompt.get(source))
            if value is not None:
                details[target] = value
    completion = usage.get("completion_tokens_details")
    if isinstance(completion, dict):
        value = _counter(completion.get("reasoning_tokens"))
        if value is not None:
            details["output_reasoning"] = value
    return details


def _usage(usage: object, input_bytes: int) -> tuple[ProviderUsage, dict[str, JsonValue]]:
    if not isinstance(usage, dict):
        return ProviderUsage(model_calls=1, input_bytes=input_bytes, reported=False), {}
    prompt = _counter(usage.get("prompt_tokens"))
    completion = _counter(usage.get("completion_tokens"))
    return (
        ProviderUsage(
            model_calls=1,
            input_bytes=input_bytes,
            input_tokens=prompt or 0,
            output_tokens=completion or 0,
            reported=prompt is not None and completion is not None,
        ),
        usage_details(usage),
    )


class BailianChatClient:
    """One pinned model on one pinned endpoint; JSON or streamed chat completions."""

    def __init__(
        self,
        *,
        profile: ModelProfile,
        endpoint: EndpointName,
        api_key: str | None,
        timeout_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if endpoint not in profile.endpoints:
            raise ValueError(f"{profile.model} is not served on the {endpoint} endpoint")
        self._profile = profile
        self._endpoint = ENDPOINTS[endpoint]
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._transport = transport
        self._semaphore = asyncio.Semaphore(1)
        self.identity = ProviderIdentity(
            id="qwen", model=profile.model, base_url=self._endpoint.base_url
        )

    async def complete(self, messages: list[dict[str, object]], *, json_mode: bool) -> Completion:
        """Send one request and parse a JSON object from the reply."""
        if not self._api_key:
            raise ProviderUnavailable(f"no key configured for the {self._endpoint.name} endpoint")
        payload: dict[str, object] = {"model": self._profile.model, "messages": messages}
        if json_mode and self._profile.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if self._profile.stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if self._profile.omni:
            payload["modalities"] = ["text"]
        input_bytes = request_body_bytes(payload)
        async with self._semaphore:
            async with httpx.AsyncClient(
                base_url=f"{self._endpoint.base_url}/",
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                try:
                    if self._profile.stream:
                        text, raw_usage = await self._stream(client, payload, input_bytes)
                    else:
                        text, raw_usage = await self._post(client, payload, input_bytes)
                except httpx.HTTPError as error:
                    raise ProviderError(
                        "evaluation model request failed",
                        failure=http_failure(error, input_bytes=input_bytes),
                    ) from error
        usage, details = _usage(raw_usage, input_bytes)
        parsed = extract_json_object(text)
        if parsed is None:
            raise ProviderError(
                "model reply did not contain a JSON object",
                failure=ProviderFailure(
                    category="invalid_response",
                    input_bytes=input_bytes,
                    input_tokens=usage.input_tokens if usage.reported else None,
                    output_tokens=usage.output_tokens if usage.reported else None,
                ),
            )
        return Completion(payload=parsed, usage=usage, details=details)

    async def _post(
        self, client: httpx.AsyncClient, payload: dict[str, object], input_bytes: int
    ) -> tuple[str, object]:
        response = await client.post("chat/completions", headers=self._headers(), json=payload)
        response.raise_for_status()
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderError(
                "model reply was not a chat completion",
                failure=ProviderFailure(category="invalid_response", input_bytes=input_bytes),
            ) from error
        if not isinstance(content, str):
            raise ProviderError(
                "model reply content was not text",
                failure=ProviderFailure(category="invalid_response", input_bytes=input_bytes),
            )
        return content, body.get("usage") if isinstance(body, dict) else None

    async def _stream(
        self, client: httpx.AsyncClient, payload: dict[str, object], input_bytes: int
    ) -> tuple[str, object]:
        pieces: list[str] = []
        usage: object = None
        async with client.stream(
            "POST", "chat/completions", headers=self._headers(), json=payload
        ) as response:
            if response.status_code >= 400:
                await response.aread()
            response.raise_for_status()
            async for line in response.aiter_lines():
                text = line.strip()
                if not text.startswith("data:"):
                    continue
                data = text[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as error:
                    raise ProviderError(
                        "stream chunk was not JSON",
                        failure=ProviderFailure(
                            category="invalid_response", input_bytes=input_bytes
                        ),
                    ) from error
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                choices = chunk.get("choices")
                if not isinstance(choices, list):
                    continue
                for choice in choices:
                    delta = choice.get("delta") if isinstance(choice, dict) else None
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(content, str):
                        pieces.append(content)
        return "".join(pieces), usage

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}


class BailianSynthesis:
    """Harness synthesis: system prompt plus typed evidence content to one model."""

    def __init__(self, client: BailianChatClient) -> None:
        self._client = client
        self.identity = client.identity

    async def synthesize(self, request: SynthesisRequest) -> Completion:
        messages: list[dict[str, object]] = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.content},
        ]
        return await self._client.complete(messages, json_mode=True)


@dataclass(frozen=True, slots=True)
class PreparedVideo:
    """The file actually sent to a native model and how it was derived."""

    path: Path
    original_bytes: int
    sent_bytes: int
    transcoded: bool
    video_kbps: int | None = None


class BailianNativeVideo:
    """Native path: the whole video as a Base64 ``video_url`` plus the task prompt."""

    def __init__(self, client: BailianChatClient, *, ffmpeg: str = "ffmpeg") -> None:
        self._client = client
        self._ffmpeg = ffmpeg
        self.identity = client.identity

    async def analyze_video(self, request: NativeRequest) -> Completion:
        prepared = await prepare_native_video(
            request.video, request.probe, request.work_dir, ffmpeg=self._ffmpeg
        )
        encoded = base64.b64encode(prepared.path.read_bytes()).decode("ascii")
        messages: list[dict[str, object]] = [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": f"data:;base64,{encoded}"}},
                    {"type": "text", "text": request.prompt},
                ],
            }
        ]
        completion = await self._client.complete(messages, json_mode=False)
        details = dict(completion.details)
        details.update(
            {
                "input_form": "video_file_base64",
                "original_bytes": prepared.original_bytes,
                "sent_bytes": prepared.sent_bytes,
                "transcoded": prepared.transcoded,
                "video_kbps": prepared.video_kbps,
            }
        )
        return Completion(payload=completion.payload, usage=completion.usage, details=details)


def _base64_size(raw_bytes: int) -> int:
    return 4 * ((raw_bytes + 2) // 3)


async def prepare_native_video(
    source: Path, probe: MediaProbe, work_dir: Path, *, ffmpeg: str = "ffmpeg"
) -> PreparedVideo:
    """Send the file as-is when it fits the Base64 limit; otherwise re-encode to fit."""
    original = source.stat().st_size
    limit = int(NATIVE_BASE64_LIMIT * _BASE64_HEADROOM)
    if _base64_size(original) <= limit:
        return PreparedVideo(source, original, original, transcoded=False)
    if shutil.which(ffmpeg) is None:
        raise ProviderError(
            "video exceeds the Base64 limit and FFmpeg is unavailable",
            failure=ProviderFailure(category="validation"),
        )
    raw_budget_bits = limit * 3 // 4 * 8
    duration = max(probe.duration_seconds, 1.0)
    total_kbps = int(raw_budget_bits / duration / 1000 * 0.9)
    audio_kbps = _AUDIO_KBPS if probe.has_audio else 0
    video_kbps = total_kbps - audio_kbps
    work_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        if video_kbps < _MIN_TRANSCODE_VIDEO_KBPS:
            break
        output = work_dir / f"native-input-{attempt}.mp4"
        command = [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            "scale='min(640,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            f"{video_kbps}k",
            "-maxrate",
            f"{video_kbps}k",
            "-bufsize",
            f"{video_kbps * 2}k",
            "-pix_fmt",
            "yuv420p",
        ]
        command += ["-c:a", "aac", "-ac", "1", "-b:a", f"{audio_kbps}k"] if audio_kbps else ["-an"]
        command.append(str(output))
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        if await process.wait() != 0:
            raise ProviderError(
                "re-encoding the native input failed",
                failure=ProviderFailure(category="media_error"),
            )
        sent = output.stat().st_size
        if _base64_size(sent) <= limit:
            return PreparedVideo(output, original, sent, transcoded=True, video_kbps=video_kbps)
        video_kbps = int(video_kbps * 0.75)
    raise ProviderError(
        "video cannot fit the Base64 limit; use a shorter clip or the upload path",
        failure=ProviderFailure(category="validation"),
    )


class EvalAsrRecognizer:
    """The harness's Qwen ASR request shape, on an endpoint that serves the model.

    Chunking and payload match ``QwenAsrRecognizer`` exactly (8 MiB Base64
    fragments of the WAV bytes) so the evaluation measures the harness
    component as released; only the endpoint differs.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        endpoint: EndpointName = "dashscope",
        timeout_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if endpoint not in ASR_ENDPOINTS:
            raise ValueError(f"{QWEN_ASR_MODEL} is not served on the {endpoint} endpoint")
        self._api_key = api_key
        self._endpoint = ENDPOINTS[endpoint]
        self._timeout = timeout_seconds
        self._transport = transport
        self._chunker = Base64AudioChunker()
        self.identity = ProviderIdentity(
            id="qwen", model=QWEN_ASR_MODEL, base_url=self._endpoint.base_url
        )

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        if not self._api_key:
            raise ProviderUnavailable(f"no key configured for the {self._endpoint.name} endpoint")
        chunks = self._chunker.encode(audio_bytes)
        texts: list[str] = []
        async with httpx.AsyncClient(
            base_url=f"{self._endpoint.base_url}/", timeout=self._timeout, transport=self._transport
        ) as client:
            for chunk in chunks:
                payload = {
                    "model": QWEN_ASR_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": f"data:{mime_type};base64,{chunk.data_base64}",
                                }
                            ],
                        }
                    ],
                }
                try:
                    response = await client.post(
                        "chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise ProviderError(
                        "ASR request failed", failure=http_failure(error, input_bytes=None)
                    ) from error
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError) as error:
                    raise ProviderError(
                        "ASR reply did not contain text",
                        failure=ProviderFailure(category="invalid_response"),
                    ) from error
                if not isinstance(content, str):
                    raise ProviderError(
                        "ASR reply content was not text",
                        failure=ProviderFailure(category="invalid_response"),
                    )
                texts.append(content)
        return TranscriptionResponse(
            text="\n".join(texts),
            usage=ProviderUsage(model_calls=len(chunks), reported=False),
        )


MOCK_IDENTITY = ProviderIdentity(id="mock", model="mock", base_url=MOCK_BASE_URL)


def _mock_usage(text: str) -> ProviderUsage:
    return ProviderUsage(
        model_calls=1, input_tokens=max(1, len(text) // 4), output_tokens=200, reported=True
    )


class MockSynthesis:
    """Offline synthesis: a deterministic schema-valid output built from the evidence."""

    identity = MOCK_IDENTITY

    async def synthesize(self, request: SynthesisRequest) -> Completion:
        output = request.task.mock_output(request.evidence, request.duration_seconds, request.item)
        return Completion(
            payload=output.model_dump(mode="json"), usage=_mock_usage(request.system_prompt)
        )


class MockNativeVideo:
    """Offline native path: a deterministic output from the probed duration only."""

    identity = MOCK_IDENTITY

    async def analyze_video(self, request: NativeRequest) -> Completion:
        output = request.task.mock_output((), request.probe.duration_seconds, request.item)
        return Completion(
            payload=output.model_dump(mode="json"),
            usage=_mock_usage(request.prompt),
            details={"input_form": "mock"},
        )


class MockRecognizer:
    """Offline ASR: a fixed sentence, so mock runs exercise the transcript path."""

    identity = ProviderIdentity(id="mock", model="mock-asr", base_url=MOCK_BASE_URL)

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        del audio_bytes, mime_type
        return TranscriptionResponse(
            text="这是离线模拟转写。它不代表视频内容。",
            usage=ProviderUsage(model_calls=0, reported=False),
        )
