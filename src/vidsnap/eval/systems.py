"""The allow-listed systems an eval run can compare, and how each is assembled."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from vidsnap.eval.adapters import (
    HarnessEvalAdapter,
    NativeEvalAdapter,
    NativePolicy,
    OracleFramesMedia,
    OracleRecognizer,
)
from vidsnap.eval.providers import (
    HARNESS_MODELS,
    MOCK_IDENTITY,
    NATIVE_MODELS,
    BailianChatClient,
    BailianNativeVideo,
    BailianSynthesis,
    EndpointName,
    EvalAsrRecognizer,
    MockNativeVideo,
    MockRecognizer,
    MockSynthesis,
    endpoint_key,
)
from vidsnap.eval.suite import EvalItem
from vidsnap.eval.tasks import EvalTask
from vidsnap.plugins.base import TranscriptionPort
from vidsnap.providers.base import ProviderIdentity
from vidsnap.runtime import FixedPolicy
from vidsnap.video.ports import FFmpegPort

SystemKind = Literal["harness", "native"]
_MODIFIERS = ("oracle-asr", "oracle-frames", "frame-labels")


@dataclass(frozen=True, slots=True)
class SystemSpec:
    """One parsed, allow-listed system name."""

    kind: SystemKind
    model: str
    oracle_asr: bool = False
    oracle_frames: bool = False
    frame_labels: bool = False

    @property
    def name(self) -> str:
        if self.kind == "native":
            return f"native:{self.model}"
        modifiers = [
            modifier
            for modifier, enabled in (
                ("oracle-asr", self.oracle_asr),
                ("oracle-frames", self.oracle_frames),
                ("frame-labels", self.frame_labels),
            )
            if enabled
        ]
        return "+".join(["harness", self.model, *modifiers])

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9.-]+", "_", self.name.lower())

    @property
    def mock(self) -> bool:
        return self.model == "mock"

    @property
    def base_name(self) -> str:
        """The plain harness system this variant is an ablation or fix of."""
        return f"harness+{self.model}" if self.kind == "harness" else self.name


def parse_system(name: str) -> SystemSpec:
    """Parse ``harness+<model>[+modifier...]`` or ``native:<model>``; refuse anything else."""
    text = name.strip()
    if text.startswith("native:"):
        model = text.removeprefix("native:")
        if model != "mock" and model not in NATIVE_MODELS:
            raise ValueError(f"native model not allow-listed: {model}")
        return SystemSpec(kind="native", model=model)
    parts = text.split("+")
    if len(parts) < 2 or parts[0] != "harness":
        raise ValueError("system must be harness+<model>[+modifier] or native:<model>")
    model = parts[1]
    if model != "mock" and model not in HARNESS_MODELS:
        raise ValueError(f"harness model not allow-listed: {model}")
    modifiers = parts[2:]
    unknown = [modifier for modifier in modifiers if modifier not in _MODIFIERS]
    if unknown or len(set(modifiers)) != len(modifiers):
        raise ValueError(f"unknown or repeated modifier: {', '.join(unknown) or 'repeated'}")
    return SystemSpec(
        kind="harness",
        model=model,
        oracle_asr="oracle-asr" in modifiers,
        oracle_frames="oracle-frames" in modifiers,
        frame_labels="frame-labels" in modifiers,
    )


def list_systems() -> list[str]:
    """Every base system name plus the modifiers a harness system accepts."""
    names = ["harness+mock", "native:mock"]
    names += [f"harness+{model}" for model in HARNESS_MODELS]
    names += [f"native:{model}" for model in NATIVE_MODELS]
    return names


@dataclass(frozen=True, slots=True)
class BuildOptions:
    endpoint: EndpointName = "dashscope"
    timeout_seconds: float = 300.0
    transport: httpx.AsyncBaseTransport | None = None


@dataclass(slots=True)
class SystemComponents:
    """What the runner hands to ``RunContext`` and ``HarnessKernel``."""

    policy: Any
    adapter: Any
    task_model: Any
    media: FFmpegPort
    recognizer: TranscriptionPort | None
    provider_identity: ProviderIdentity
    recognizer_identity: ProviderIdentity | None


class NotApplicable(Exception):
    """The system cannot run on this item (for example an oracle without a reference)."""


def build_components(
    spec: SystemSpec,
    task: EvalTask[Any],
    item: EvalItem,
    *,
    media: FFmpegPort,
    options: BuildOptions,
) -> SystemComponents:
    """Assemble one system for one item; raise ``NotApplicable`` when it cannot run."""
    if spec.kind == "native":
        port: Any
        if spec.mock:
            port = MockNativeVideo()
        else:
            profile = NATIVE_MODELS[spec.model]
            endpoint = _endpoint_for(profile.endpoints, options.endpoint)
            port = BailianNativeVideo(
                BailianChatClient(
                    profile=profile,
                    endpoint=endpoint,
                    api_key=endpoint_key(endpoint),
                    timeout_seconds=options.timeout_seconds,
                    transport=options.transport,
                )
            )
        return SystemComponents(
            policy=NativePolicy(),
            adapter=NativeEvalAdapter(task, item),
            task_model=port,
            media=media,
            recognizer=None,
            provider_identity=port.identity,
            recognizer_identity=None,
        )

    synthesis: Any
    if spec.mock:
        synthesis = MockSynthesis()
    else:
        profile = HARNESS_MODELS[spec.model]
        endpoint = _endpoint_for(profile.endpoints, options.endpoint)
        synthesis = BailianSynthesis(
            BailianChatClient(
                profile=profile,
                endpoint=endpoint,
                api_key=endpoint_key(endpoint),
                timeout_seconds=options.timeout_seconds,
                transport=options.transport,
            )
        )
    recognizer: Any
    if spec.oracle_asr:
        transcript = item.reference.transcript
        if transcript is None or not transcript.segments:
            raise NotApplicable("oracle-asr needs a reference transcript")
        recognizer = OracleRecognizer(transcript.text())
    elif spec.mock:
        recognizer = MockRecognizer()
    else:
        recognizer = EvalAsrRecognizer(
            api_key=endpoint_key("dashscope"),
            endpoint="dashscope",
            timeout_seconds=options.timeout_seconds,
            transport=options.transport,
        )
    if spec.oracle_frames:
        if not item.reference.key_moments:
            raise NotApplicable("oracle-frames needs reference key moments")
        media = OracleFramesMedia(media, item.reference.key_moments)
    return SystemComponents(
        policy=FixedPolicy(),
        adapter=HarnessEvalAdapter(task, item, frame_labels=spec.frame_labels),
        task_model=synthesis,
        media=media,
        recognizer=recognizer,
        provider_identity=synthesis.identity if not spec.mock else MOCK_IDENTITY,
        recognizer_identity=recognizer.identity,
    )


def _endpoint_for(allowed: tuple[EndpointName, ...], requested: EndpointName) -> EndpointName:
    if requested in allowed:
        return requested
    return allowed[0]
