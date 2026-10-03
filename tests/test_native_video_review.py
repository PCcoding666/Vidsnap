"""Offline tests for the native-video two-route review runner.

Everything here is deterministic: fake provider/media/ASR boundaries, the real
HarnessKernel, no network, no live models, no real media decoding.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import io
import json
import sys
import wave
from pathlib import Path

import pytest

import vidsnap
from vidsnap.contracts.agent import AgentDecision, ProviderUsage
from vidsnap.providers.base import (
    AgentDecisionFormatError,
    AgentDecisionResponse,
    ProviderIdentity,
)
from vidsnap.providers.local_whisper import LocalWhisperTranscriber
from vidsnap.providers.native_video import (
    MAX_INLINE_BASE64_BYTES,
    NativeVideoError,
    NativeVideoResult,
)
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "native_video_review.py"

spec = importlib.util.spec_from_file_location("native_video_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
sys.modules["native_video_review"] = review
spec.loader.exec_module(review)

CLIP_PROBE = MediaProbe(duration_seconds=80.0, fps=24.0, width=1280, height=720, has_audio=True)
ORIGINAL_PROBE = MediaProbe(
    duration_seconds=600.0, fps=24.0, width=1920, height=1080, has_audio=True
)
OFFSET = 120.0


def _silent_wav_bytes(seconds: float = 0.5, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


class _FakeMedia:
    """FFmpegPort fake: probed metadata, tiny real WAV, fake JPEG frames."""

    def __init__(self, *, candidate_count: int = 2) -> None:
        self.sampler = AdaptiveSampler()
        self.probe_calls = 0
        self.audio_calls = 0
        self.frame_extract_calls = 0
        self._candidate_count = candidate_count

    async def probe(self, source: Path) -> MediaProbe:
        self.probe_calls += 1
        if source.name.startswith("original"):
            return ORIGINAL_PROBE
        return CLIP_PROBE

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        return [
            FrameCandidate(
                timestamp=min(5.0 + 2.0 * index, probe.duration_seconds - 1.0),
                score=0.5,
                perceptual_hash=f"ph{index}",
            )
            for index in range(self._candidate_count)
        ]

    async def extract_frames(self, source, candidates, output_dir):
        self.frame_extract_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index, candidate in enumerate(candidates):
            frame_path = output_dir / f"frame-{index:03d}.jpg"
            frame_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_timeline_frames(self, source, *, fps, output_dir):
        raise AssertionError("agentic route must not build a direct baseline")

    async def extract_audio(self, source, output_path, *, start_seconds=0.0, end_seconds=None):
        self.audio_calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_silent_wav_bytes())
        return output_path


async def _fake_whisper_runner(
    *, executable, audio_path, output_dir, model_path, env, timeout_seconds
) -> int:
    (output_dir / f"{audio_path.stem}.txt").write_text("离线假转写文本", encoding="utf-8")
    return 0


def _whisper(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "whisper-cli"
    executable.write_bytes(b"#!/bin/sh\n")
    model = tmp_path / "ggml-model.bin"
    model.write_bytes(b"fake-weights")
    return executable, model


def _transcriber(tmp_path: Path) -> LocalWhisperTranscriber:
    executable, model = _whisper(tmp_path)
    return LocalWhisperTranscriber(
        executable=executable, model_path=model, runner=_fake_whisper_runner
    )


def _clip(tmp_path: Path) -> Path:
    clip = tmp_path / "clip.mkv"  # real evaluation input is MKV (AV1+Opus)
    clip.write_bytes(b"\x1a\x45\xdf\xa3" * 1024)
    return clip


def _original(tmp_path: Path) -> Path:
    original = tmp_path / "original.mp4"
    original.write_bytes(b"\x09\x08\x07\x06" * 2048)
    return original


class _FakeNativeClient:
    """Native fake: records calls, returns or raises deterministically."""

    identity = ProviderIdentity(
        id="bailian-native-video",
        model="qwen3.5-omni-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    def __init__(self, *, error: NativeVideoError | None = None, reported: bool = False) -> None:
        self.calls: list[tuple[object, str]] = []
        self._error = error
        self._reported = reported

    async def analyze_clip(self, clip, *, task: str) -> NativeVideoResult:
        self.calls.append((clip, task))
        if self._error is not None:
            raise self._error
        return NativeVideoResult(
            text="<script>alert(1)</script>原生笔记：片头介绍了主题 [00:05]",
            usage=ProviderUsage(
                model_calls=1,
                input_bytes=4321,
                input_tokens=100 if self._reported else 0,
                output_tokens=50 if self._reported else 0,
                reported=self._reported,
            ),
            identity=self.identity,
            request_bytes=4321,
        )


_FINAL_OUTPUT = {
    "summary": "Harness离线假摘要",
    "claims": [
        {
            "text": "转写提到主题 <b>加粗</b>",
            "evidence": [{"evidence_id": "transcript-001"}],
        },
        {
            "text": "画面证据支持",
            "evidence": [{"evidence_id": "frame-001"}],
        },
    ],
}


class _FakeHarnessProvider:
    """Agentic fake: transcribe, sample, then final — three decisions total."""

    identity = ProviderIdentity(
        id="qwen", model="qwen3.8-max", base_url="https://token-plan.invalid/v1"
    )

    def __init__(self) -> None:
        self.decide_calls = 0

    async def decide_next(self, request) -> AgentDecisionResponse:
        self.decide_calls += 1
        if self.decide_calls == 1:
            payload = {"kind": "tool_calls", "calls": [{"name": "transcribe_audio"}]}
        elif self.decide_calls == 2:
            payload = {
                "kind": "tool_calls",
                "calls": [{"name": "sample_evidence", "arguments": {"max_frames": 4}}],
            }
        else:
            payload = {"kind": "final", "output": _FINAL_OUTPUT}
        return AgentDecisionResponse(
            decision=AgentDecision.model_validate(payload),
            usage=ProviderUsage(model_calls=1, input_bytes=500 + self.decide_calls, reported=False),
        )


class _BadJsonHarnessProvider(_FakeHarnessProvider):
    """Agentic fake whose very first decision is malformed."""

    async def decide_next(self, request) -> AgentDecisionResponse:
        self.decide_calls += 1
        raise AgentDecisionFormatError("model returned malformed JSON")


class _BadFinalHarnessProvider(_FakeHarnessProvider):
    """Agentic fake whose first final cites evidence that does not exist."""

    async def decide_next(self, request) -> AgentDecisionResponse:
        self.decide_calls += 1
        if self.decide_calls == 1:
            payload = {"kind": "tool_calls", "calls": [{"name": "transcribe_audio"}]}
        else:
            payload = {
                "kind": "final",
                "output": {
                    "summary": "未核验摘要",
                    "claims": [
                        {"text": "伪造引用", "evidence": [{"evidence_id": "frame-999"}]},
                    ],
                },
            }
        return AgentDecisionResponse(
            decision=AgentDecision.model_validate(payload),
            usage=ProviderUsage(model_calls=1, input_bytes=500 + self.decide_calls, reported=False),
        )


class _GreedyFrameProvider(_FakeHarnessProvider):
    """Agentic fake requesting more frames than the total remaining budget."""

    async def decide_next(self, request) -> AgentDecisionResponse:
        self.decide_calls += 1
        payload = {
            "kind": "tool_calls",
            "calls": [{"name": "sample_evidence", "arguments": {"max_frames": 25}}],
        }
        return AgentDecisionResponse(
            decision=AgentDecision.model_validate(payload),
            usage=ProviderUsage(model_calls=1, input_bytes=500 + self.decide_calls, reported=False),
        )


class _CumulativeFrameProvider(_FakeHarnessProvider):
    """Agentic fake whose second sample exceeds the budget left by the first."""

    async def decide_next(self, request) -> AgentDecisionResponse:
        self.decide_calls += 1
        max_frames = 20 if self.decide_calls == 1 else 12
        payload = {
            "kind": "tool_calls",
            "calls": [{"name": "sample_evidence", "arguments": {"max_frames": max_frames}}],
        }
        return AgentDecisionResponse(
            decision=AgentDecision.model_validate(payload),
            usage=ProviderUsage(model_calls=1, input_bytes=500 + self.decide_calls, reported=False),
        )


def test_validate_only_creates_nothing_and_reports_provenance(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    executable, model = _whisper(tmp_path)
    output = tmp_path / "review_out"
    media = _FakeMedia()
    before = set(tmp_path.iterdir())
    summary = asyncio.run(
        review.validate_only(
            video=clip,
            original_source=original,
            source_offset=OFFSET,
            output=output,
            whisper_executable=executable,
            whisper_model=model,
            media=media,
        )
    )
    assert set(tmp_path.iterdir()) == before  # validate-only creates nothing
    assert not output.exists()
    assert media.probe_calls == 2  # clip + original only; no ASR, no model calls
    assert summary["mode"] == "validate-only"
    assert summary["clip_sha256"] == hashlib.sha256(clip.read_bytes()).hexdigest()
    assert summary["original_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert summary["source_offset"] == OFFSET
    assert summary["clip"]["duration_seconds"] == 80.0
    assert summary["task_hash"] == hashlib.sha256(review.COMMON_TASK.encode()).hexdigest()
    assert 0 < summary["clip"]["base64_bytes"] < MAX_INLINE_BASE64_BYTES


def test_validate_only_rejects_offset_outside_original(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    executable, model = _whisper(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(
            review.validate_only(
                video=clip,
                original_source=original,
                source_offset=550.0,  # 550 + 80 > 600
                output=tmp_path / "out",
                whisper_executable=executable,
                whisper_model=model,
                media=_FakeMedia(),
            )
        )
    with pytest.raises(ValueError):
        asyncio.run(
            review.validate_only(
                video=clip,
                original_source=original,
                source_offset=-1.0,
                output=tmp_path / "out",
                whisper_executable=executable,
                whisper_model=model,
                media=_FakeMedia(),
            )
        )


def test_validate_only_requires_real_whisper_files(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    executable, model = _whisper(tmp_path)
    missing = tmp_path / "missing-model.bin"
    with pytest.raises(ValueError):
        asyncio.run(
            review.validate_only(
                video=clip,
                original_source=original,
                source_offset=OFFSET,
                output=tmp_path / "out",
                whisper_executable=executable,
                whisper_model=missing,
                media=_FakeMedia(),
            )
        )
    empty_model = tmp_path / "empty.bin"
    empty_model.write_bytes(b"")
    with pytest.raises(ValueError):
        asyncio.run(
            review.validate_only(
                video=clip,
                original_source=original,
                source_offset=OFFSET,
                output=tmp_path / "out",
                whisper_executable=executable,
                whisper_model=empty_model,
                media=_FakeMedia(),
            )
        )


def test_ensure_output_dir_rejects_forbidden_occupied_and_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fresh = tmp_path / "fresh"
    review.ensure_output_dir(fresh, forbidden_roots=(repo,))
    assert not fresh.exists()

    with pytest.raises(ValueError):
        review.ensure_output_dir(repo / "inside", forbidden_roots=(repo,))

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("do not touch")
    with pytest.raises(ValueError):
        review.ensure_output_dir(occupied, forbidden_roots=(repo,))
    assert (occupied / "keep.txt").read_text() == "do not touch"

    link = tmp_path / "link"
    link.symlink_to(repo)
    with pytest.raises(ValueError):
        review.ensure_output_dir(link / "through-symlink", forbidden_roots=(repo,))


def test_run_review_native_failure_stops_before_harness(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    output_dir = tmp_path / "review_out"
    executable, model = _whisper(tmp_path)
    native = _FakeNativeClient(
        error=NativeVideoError(
            "Native video request failed with an HTTP error.",
            category="http_error",
            http_status=429,
            request_bytes=2048,
            attempts=1,
        )
    )
    harness = _FakeHarnessProvider()
    report = asyncio.run(
        review.run_review(
            video=clip,
            original_source=original,
            source_offset=OFFSET,
            output_dir=output_dir,
            native_client=native,
            harness_client=harness,
            media=_FakeMedia(),
            whisper_runner=_fake_whisper_runner,
            whisper_executable=executable,
            whisper_model=model,
            forbidden_roots=(REPO_ROOT,),
        )
    )
    assert len(native.calls) == 1
    assert harness.decide_calls == 0  # harness route never ran
    native_section = report["routes"]["native"]
    assert native_section["status"] == "failed"
    assert native_section["failure"]["category"] == "http_error"
    assert native_section["failure"]["http_status"] == 429
    assert native_section["failure"]["request_bytes"] == 2048  # serialized, not received
    assert native_section["failure"]["attempts"] == 1
    assert native_section["failure"]["request_sent"] is True  # HTTP response confirms
    assert isinstance(native_section["latency_ms"], int)  # real terminal duration
    assert native_section["usage"]["model_calls"] == 1  # one attempt was made
    assert native_section["usage"]["input_tokens"] is None
    assert native_section["usage"]["output_tokens"] is None
    assert native_section["frames"] is None  # native internal frames stay unknown
    assert native_section["input_mode"] == "native_video"
    assert native_section["has_audio"] is True
    assert "harness" not in report["routes"]
    assert (output_dir / "report.json").is_file()
    assert (output_dir / "native-trace.html").is_file()
    native_events = [
        json.loads(line)
        for line in (output_dir / "native" / "events.jsonl").read_text().splitlines()
    ]
    native_types = [e.get("event_type") for e in native_events]
    assert "model.request.started" in native_types
    assert "model.request.failed" in native_types
    native_manifest = json.loads((output_dir / "native" / "manifest.json").read_text())
    assert native_manifest["terminal_state"] == "FAILED"
    page = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "http_error" in page
    assert "Traceback" not in page
    assert "NativeVideoError(" not in page  # no repr of the exception object
    assert "Bearer" not in page and "sk-" not in page
    persisted = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert persisted["routes"]["native"]["failure"]["category"] == "http_error"


def test_run_review_end_to_end_with_real_kernel(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    output_dir = tmp_path / "review_out"
    executable, model = _whisper(tmp_path)
    native = _FakeNativeClient(reported=False)
    harness = _FakeHarnessProvider()
    report = asyncio.run(
        review.run_review(
            video=clip,
            original_source=original,
            source_offset=OFFSET,
            output_dir=output_dir,
            native_client=native,
            harness_client=harness,
            media=_FakeMedia(),
            whisper_runner=_fake_whisper_runner,
            whisper_executable=executable,
            whisper_model=model,
            forbidden_roots=(REPO_ROOT,),
        )
    )
    # Fixed common task reached the native route verbatim.
    assert native.calls[0][1] == review.COMMON_TASK
    assert harness.decide_calls == 3

    provenance = report["provenance"]
    assert provenance["clip_sha256"] == hashlib.sha256(clip.read_bytes()).hexdigest()
    assert provenance["original_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert provenance["source_offset"] == OFFSET
    assert provenance["task_hash"] == hashlib.sha256(review.COMMON_TASK.encode()).hexdigest()
    assert provenance["code_version"] == vidsnap.__version__
    assert provenance["code_hashes"]["scripts/native_video_review.py"]
    assert "runtime/kernel.py" in provenance["code_hashes"]  # src/vidsnap/**/*.py covered
    budgets = report["budgets"]
    assert budgets["max_model_calls"] == 6
    assert budgets["max_tool_calls"] == 4
    assert budgets["max_evidence_frames"] == 24
    assert budgets["max_wall_seconds"] == 900

    native_section = report["routes"]["native"]
    assert native_section["status"] == "completed"
    assert native_section["request_bytes"] == 4321
    assert native_section["trace"] == "native-trace.html"
    assert native_section["frames"] is None  # internal frames unknown, never invented
    assert native_section["input_mode"] == "native_video"
    assert native_section["has_audio"] is True
    assert native_section["usage"]["model_calls"] == 1
    assert native_section["usage"]["input_tokens"] is None  # unreported stays unknown
    assert native_section["usage"]["output_tokens"] is None
    assert native_section["latency_ms"] is not None
    assert "原生笔记" in native_section["text"]
    # Validated native notes are persisted in the bundle before finalization.
    native_notes = json.loads((output_dir / "native" / "result.json").read_text())
    assert native_notes["text"] == native_section["text"]
    assert report["review_completed"] is True

    harness_section = report["routes"]["harness"]
    assert harness_section["terminal_state"] == "SUCCEEDED"
    assert harness_section["usage"]["model_calls"] == 3  # remote calls only
    assert harness_section["usage"]["input_tokens"] is None  # unreported fake
    assert harness_section["frames"] == 2
    assert harness_section["latency_ms"] is not None
    assert harness_section["verification"]["gates"]["schema_valid"] is True
    local_asr = harness_section["local_asr"]
    assert local_asr["calls"] == 1  # started executions only, separate from remote calls
    assert local_asr["attempts"] == 1
    assert local_asr["completed"] == 1
    assert local_asr["returncode_unknown"] == 0
    assert local_asr["audio_seconds"] == pytest.approx(0.5)
    assert local_asr["audio_bytes"] > 0
    assert local_asr["executions"][0]["status"] == "completed"
    assert local_asr["executions"][0]["returncode"] == 0
    assert harness_section["events"]  # real kernel events, not invented dicts
    event_types = [e.get("event_type") for e in harness_section["events"]]
    assert event_types[0] == "runtime.configuration"  # config recorded before execution
    assert "local.asr.started" in event_types
    assert "local.asr.completed" in event_types
    assert event_types.index("local.asr.started") < event_types.index("local.asr.completed")
    config_payload = harness_section["events"][0]["payload"]
    assert config_payload["task_hash"] == provenance["task_hash"]
    assert config_payload["budgets"]["max_model_calls"] == 6
    assert config_payload["registered_tools"] == ["transcribe_audio", "sample_evidence"]
    assert config_payload["controls"] == {
        "policy": "FailFastAgenticPolicy",
        "format_repair": "disabled",
        "verifier_repair": "disabled",
        "pre_execution_frame_cap": "enabled",
    }
    assert "VIDSNAP" not in json.dumps(config_payload)  # no environment dump

    # Native route also has a real bundle with started/completed trace pairs.
    native_events = [
        json.loads(line)
        for line in (output_dir / "native" / "events.jsonl").read_text().splitlines()
    ]
    native_types = [e.get("event_type") for e in native_events]
    assert native_types[0] == "runtime.configuration"
    native_config = native_events[0]["payload"]
    assert native_config["registered_tools"] == []  # native route exposes no tools
    assert native_config["frames_budget"] == "not_applicable"  # placeholder made explicit
    assert "run.started" in native_types
    run_started = native_events[native_types.index("run.started")]
    assert run_started["payload"]["source_sha256"] == provenance["clip_sha256"]
    assert run_started["payload"]["goal"]
    assert "model.request.started" in native_types
    assert "model.request.completed" in native_types
    assert native_types.index("model.request.started") < native_types.index(
        "model.request.completed"
    )
    native_manifest = json.loads((output_dir / "native" / "manifest.json").read_text())
    assert native_manifest["terminal_state"] == "SUCCEEDED"
    assert native_manifest["finalized_at"] is not None
    # Bundles record the real route budgets, not loop-spec defaults.
    assert native_manifest["resources"]["max_model_calls"] == 1
    assert native_manifest["resources"]["max_tool_calls"] == 0
    assert native_manifest["resources"]["max_wall_seconds"] == 300
    harness_manifest = json.loads((output_dir / "harness" / "manifest.json").read_text())
    assert harness_manifest["resources"]["max_model_calls"] == 6
    assert harness_manifest["resources"]["max_tool_calls"] == 4
    assert harness_manifest["resources"]["max_evidence_frames"] == 24
    assert harness_manifest["resources"]["max_wall_seconds"] == 900

    assert (output_dir / "harness" / "manifest.json").is_file()
    assert (output_dir / "harness-trace.html").is_file()
    assert (output_dir / "native-trace.html").is_file()
    # The copied clip keeps its real MKV extension and bytes — never renamed to mp4.
    assert (output_dir / "clip.mkv").read_bytes() == clip.read_bytes()
    assert not (output_dir / "clip.mp4").exists()
    page = (output_dir / "index.html").read_text(encoding="utf-8")
    assert 'href="clip.mkv"' in page  # real file link for non-browser-playable MKV
    assert 'download="clip.mkv"' in page
    assert "<video" not in page  # no fake player pretending the MKV was transcoded
    assert "<script>alert(1)</script>" not in page  # native text escaped
    assert "&lt;script&gt;" in page
    assert "<b>加粗</b>" not in page  # claim text escaped
    assert 'href="native-trace.html"' in page  # both real traces linked
    assert 'href="harness-trace.html"' in page
    assert "内部帧数未知" in page  # native internal frames explicitly unknown
    assert "未经独立核验" in page  # native timestamps disclaimer
    assert "仅整体方案对照" in page  # no superiority claim
    assert "Bearer" not in page and "sk-" not in page
    # No environment dump anywhere in persisted artifacts.
    report_text = (output_dir / "report.json").read_text(encoding="utf-8")
    assert "VIDSNAP_QWEN_API_KEY" not in report_text
    assert "VIDSNAP_MODEL_STUDIO_UPLOAD_API_KEY" not in report_text


def test_run_review_native_reported_tokens_flow_through(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    executable, model = _whisper(tmp_path)
    report = asyncio.run(
        review.run_review(
            video=clip,
            original_source=original,
            source_offset=OFFSET,
            output_dir=tmp_path / "review_out",
            native_client=_FakeNativeClient(reported=True),
            harness_client=_FakeHarnessProvider(),
            media=_FakeMedia(),
            whisper_runner=_fake_whisper_runner,
            whisper_executable=executable,
            whisper_model=model,
            forbidden_roots=(REPO_ROOT,),
        )
    )
    usage = report["routes"]["native"]["usage"]
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["reported"] is True


def test_run_review_refuses_existing_output(tmp_path: Path) -> None:
    clip = _clip(tmp_path)
    original = _original(tmp_path)
    output_dir = tmp_path / "review_out"
    output_dir.mkdir()
    (output_dir / "previous.txt").write_text("earlier evidence")
    executable, model = _whisper(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(
            review.run_review(
                video=clip,
                original_source=original,
                source_offset=OFFSET,
                output_dir=output_dir,
                native_client=_FakeNativeClient(),
                harness_client=_FakeHarnessProvider(),
                media=_FakeMedia(),
                whisper_runner=_fake_whisper_runner,
                whisper_executable=tmp_path / "whisper-cli",
                whisper_model=tmp_path / "ggml-model.bin",
                forbidden_roots=(REPO_ROOT,),
            )
        )
    assert (output_dir / "previous.txt").read_text() == "earlier evidence"


def _run_kwargs(tmp_path: Path) -> dict:
    executable, model = _whisper(tmp_path)
    return {
        "video": _clip(tmp_path),
        "original_source": _original(tmp_path),
        "source_offset": OFFSET,
        "output_dir": tmp_path / "review_out",
        "native_client": _FakeNativeClient(),
        "harness_client": _FakeHarnessProvider(),
        "media": _FakeMedia(),
        "whisper_runner": _fake_whisper_runner,
        "whisper_executable": executable,
        "whisper_model": model,
        "forbidden_roots": (REPO_ROOT,),
    }


def test_run_review_native_unavailable_marks_request_not_sent(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    kwargs["native_client"] = _FakeNativeClient(
        error=NativeVideoError("No local Bailian key.", category="unavailable", attempts=0)
    )
    report = asyncio.run(review.run_review(**kwargs))
    failure = report["routes"]["native"]["failure"]
    assert failure["category"] == "unavailable"
    assert failure["request_sent"] is False  # attempts=0 means no remote request went out
    assert report["routes"]["native"]["usage"]["model_calls"] == 0
    assert "harness" not in report["routes"]


def test_run_review_native_network_error_marks_request_unknown(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    kwargs["native_client"] = _FakeNativeClient(
        error=NativeVideoError(
            "Native video request failed with a network error.",
            category="network_error",
            request_bytes=1024,
            attempts=1,
        )
    )
    report = asyncio.run(review.run_review(**kwargs))
    failure = report["routes"]["native"]["failure"]
    assert failure["category"] == "network_error"
    assert failure["request_sent"] is None  # network failure: receipt unknowable
    assert failure["request_bytes"] == 1024  # serialized bytes, not provider-received
    assert "harness" not in report["routes"]


class _ExplodingNativeClient(_FakeNativeClient):
    async def analyze_clip(self, clip, *, task: str):
        self.calls.append((clip, task))
        raise RuntimeError("unexpected SDK failure at /secret/sdk/path")


def test_run_review_native_unexpected_error_is_safe_and_finalized(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    kwargs["native_client"] = _ExplodingNativeClient()
    report = asyncio.run(review.run_review(**kwargs))
    native = report["routes"]["native"]
    assert native["status"] == "failed"
    assert native["failure"]["category"] == "unexpected_error"
    assert native["failure"]["failure_class"] == "RuntimeError"
    assert isinstance(native["latency_ms"], int)  # real terminal duration recorded
    # Unobserved exception: counters stay unknown, never fabricated zeros.
    assert native["usage"]["model_calls"] is None
    assert native["usage"]["input_bytes"] is None
    assert native["usage"]["input_tokens"] is None
    assert native["usage"]["output_tokens"] is None
    assert native["usage"]["reported"] is False
    assert "harness" not in report["routes"]
    output_dir = tmp_path / "review_out"
    native_manifest = json.loads((output_dir / "native" / "manifest.json").read_text())
    assert native_manifest["terminal_state"] == "FAILED"  # no unfinalized bundle left
    assert native_manifest["finalized_at"] is not None
    persisted = (output_dir / "report.json").read_text(encoding="utf-8")
    assert "/secret/sdk/path" not in persisted  # no raw exception text
    assert "unexpected SDK failure" not in persisted


def test_local_asr_summary_counts_started_only(tmp_path: Path) -> None:
    from vidsnap.providers.local_whisper import LocalWhisperExecution

    def _record(*, status: str, attempted: bool, started: bool, returncode: int | None):
        return LocalWhisperExecution(
            model_path=tmp_path / "model.bin",
            audio_bytes=16,
            audio_seconds=0.5,
            duration_seconds=0.25,
            status=status,
            attempted=attempted,
            started=started,
            returncode=returncode,
        )

    records = [
        _record(status="completed", attempted=True, started=True, returncode=0),
        _record(status="failed", attempted=True, started=False, returncode=None),  # spawn failed
        _record(status="failed", attempted=True, started=True, returncode=None),  # timeout
    ]
    summary = review._local_asr_summary(records)
    assert summary["attempts"] == 3
    assert summary["calls"] == 2  # only executions that actually started
    assert summary["completed"] == 1
    assert summary["returncode_unknown"] == 2
    assert summary["executions"][1]["returncode"] is None


def test_validate_only_rejects_existing_output_even_when_empty(tmp_path: Path) -> None:
    executable, model = _whisper(tmp_path)
    empty = tmp_path / "empty_out"
    empty.mkdir()
    with pytest.raises(ValueError):
        asyncio.run(
            review.validate_only(
                video=_clip(tmp_path),
                original_source=_original(tmp_path),
                source_offset=OFFSET,
                output=empty,
                whisper_executable=executable,
                whisper_model=model,
                media=_FakeMedia(),
                forbidden_roots=(REPO_ROOT,),
            )
        )


def test_validate_only_rejects_non_finite_offset(tmp_path: Path) -> None:
    executable, model = _whisper(tmp_path)
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            asyncio.run(
                review.validate_only(
                    video=_clip(tmp_path),
                    original_source=_original(tmp_path),
                    source_offset=bad,
                    output=tmp_path / "out",
                    whisper_executable=executable,
                    whisper_model=model,
                    media=_FakeMedia(),
                    forbidden_roots=(REPO_ROOT,),
                )
            )


def test_default_forbidden_roots_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(review.subprocess, "run", _boom)
    with pytest.raises(ValueError):
        review.default_forbidden_roots()

    class _Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(review.subprocess, "run", lambda *args, **kwargs: _Result())
    with pytest.raises(ValueError):
        review.default_forbidden_roots()


def test_main_reads_keys_only_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    async def _stub_run_review(**kwargs):
        captured.update(kwargs)
        return {
            "review_completed": True,
            "routes": {
                "native": {"status": "completed"},
                "harness": {"terminal_state": "SUCCEEDED"},
            },
        }

    monkeypatch.setattr(review, "run_review", _stub_run_review)
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", "test-qwen-key-123")
    monkeypatch.setenv("VIDSNAP_MODEL_STUDIO_UPLOAD_API_KEY", "test-ms-key-456")
    argv = [
        "--video",
        str(tmp_path / "clip.mkv"),
        "--original-source",
        str(tmp_path / "original.mp4"),
        "--source-offset",
        "120",
        "--output",
        str(tmp_path / "out"),
        "--whisper-executable",
        str(tmp_path / "whisper-cli"),
        "--whisper-model",
        str(tmp_path / "model.bin"),
    ]
    assert review.main(argv) == 0
    native_client = captured["native_client"]
    harness_client = captured["harness_client"]
    assert native_client._api_key == "test-ms-key-456"
    assert harness_client._api_key == "test-qwen-key-123"
    assert native_client.identity.model == "qwen3.5-omni-plus"  # models stay pinned
    assert harness_client.identity.model == "qwen3.8-max"

    monkeypatch.delenv("VIDSNAP_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("VIDSNAP_MODEL_STUDIO_UPLOAD_API_KEY", raising=False)
    assert review.main(argv) == 0
    assert captured["native_client"]._api_key is None
    assert captured["harness_client"]._api_key is None


def test_main_exit_nonzero_when_review_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _stub_run_review(**kwargs):
        return {
            "review_completed": False,  # e.g. a trace_export_error with success status
            "routes": {
                "native": {"status": "completed", "trace_export_error": "RuntimeError"},
                "harness": {"terminal_state": "SUCCEEDED"},
            },
        }

    monkeypatch.setattr(review, "run_review", _stub_run_review)
    argv = [
        "--video",
        str(tmp_path / "clip.mkv"),
        "--original-source",
        str(tmp_path / "original.mp4"),
        "--source-offset",
        "120",
        "--output",
        str(tmp_path / "out"),
        "--whisper-executable",
        str(tmp_path / "whisper-cli"),
        "--whisper-model",
        str(tmp_path / "model.bin"),
    ]
    assert review.main(argv) == 1  # terminal_state alone must not mean success


def test_harness_export_failure_preserves_completed_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_export = review.export_trace

    def _flaky_export(source, output):
        if Path(output).name == "harness-trace.html":
            raise RuntimeError("injected disk failure at /secret/internal/path")
        return real_export(source, output)

    monkeypatch.setattr(review, "export_trace", _flaky_export)
    report = asyncio.run(review.run_review(**_run_kwargs(tmp_path)))
    assert report["routes"]["native"]["status"] == "completed"  # checkpoint preserved
    harness = report["routes"]["harness"]
    # The completed run's usage/output/gates survive an export failure.
    assert harness["terminal_state"] == "SUCCEEDED"
    assert harness["trace_export_error"] == "RuntimeError"
    assert harness["usage"]["model_calls"] == 3
    assert harness["output"]["summary"] == "Harness离线假摘要"
    assert harness["verification"]["gates"]["schema_valid"] is True
    # But the review delivery is incomplete — not a success for the next video.
    assert report["review_completed"] is False
    output_dir = tmp_path / "review_out"
    assert (output_dir / "report.json").is_file()
    assert (output_dir / "native-trace.html").is_file()
    persisted = (output_dir / "report.json").read_text(encoding="utf-8")
    assert "injected disk failure" not in persisted  # no raw exception text
    assert "/secret/internal/path" not in persisted


def test_native_export_failure_preserves_success_and_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _flaky_export(source, output):
        raise RuntimeError("injected export failure at /secret/export/path")

    monkeypatch.setattr(review, "export_trace", _flaky_export)
    kwargs = _run_kwargs(tmp_path)
    harness_client = kwargs["harness_client"]
    report = asyncio.run(review.run_review(**kwargs))
    native = report["routes"]["native"]
    assert native["status"] == "completed"  # the real model call is not erased
    assert native["trace_export_error"] == "RuntimeError"
    assert native["usage"]["model_calls"] == 1
    assert native["request_bytes"] == 4321
    assert "原生笔记" in native["text"]
    # An export failure is not review success: Harness must not run next.
    assert harness_client.decide_calls == 0
    assert "harness" not in report["routes"]
    assert report["review_completed"] is False
    output_dir = tmp_path / "review_out"
    assert (output_dir / "report.json").is_file()
    native_manifest = json.loads((output_dir / "native" / "manifest.json").read_text())
    assert native_manifest["terminal_state"] == "SUCCEEDED"
    persisted = (output_dir / "report.json").read_text(encoding="utf-8")
    assert "injected export failure" not in persisted
    assert "/secret/export/path" not in persisted


def test_render_report_unknown_citation_is_not_faked() -> None:
    report = {
        "synthetic": False,
        "provenance": {
            "clip_sha256": "ab" * 32,
            "original_sha256": "cd" * 32,
            "source_offset": 120.0,
            "task_hash": "ef" * 32,
        },
        "clip_file": "clip.mkv",
        "routes": {
            "harness": {
                "terminal_state": "SUCCEEDED",
                "usage": {},
                "events": [],
                "frames": 1,
                "latency_ms": 10,
                "local_asr": {"calls": 0, "audio_seconds": 0.0, "audio_bytes": 0},
                "evidence": [
                    {
                        "id": "frame-001",
                        "start_seconds": 10,
                        "end_seconds": 10,
                        "modality": "frame",
                    }
                ],
                "output": {
                    "summary": "s",
                    "claims": [
                        {"text": "known", "evidence": [{"evidence_id": "frame-001"}]},
                        {"text": "unknown", "evidence": [{"evidence_id": "frame-999"}]},
                    ],
                },
            },
        },
    }
    page = review.render_report(report)
    assert "原片 130s" in page  # 120 offset + 10s for the known citation
    assert "未知" in page  # unknown citation is marked, not faked as 0s
    assert "原片 0s" not in page


def test_fail_fast_policy_records_first_format_error(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    harness = _BadJsonHarnessProvider()
    kwargs["harness_client"] = harness
    report = asyncio.run(review.run_review(**kwargs))
    assert report["routes"]["native"]["status"] == "completed"
    assert harness.decide_calls == 1  # no format-repair resend of the bad JSON
    section = report["routes"]["harness"]
    assert section["terminal_state"] == "FAILED"
    assert report["review_completed"] is False
    event_types = [e.get("event_type") for e in section["events"]]
    assert event_types.count("model.request.started") == 1  # exactly one model call
    assert "model.request.failed" in event_types
    assert "repair.requested" not in event_types
    decision_events = [e for e in section["events"] if e.get("event_type") == "agent.decision"]
    assert decision_events[0]["payload"]["reason"] == "format_error"
    manifest = json.loads((tmp_path / "review_out" / "harness" / "manifest.json").read_text())
    assert manifest["terminal_state"] == "FAILED"


def test_fail_fast_policy_stops_after_first_failed_verification(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    harness = _BadFinalHarnessProvider()
    kwargs["harness_client"] = harness
    report = asyncio.run(review.run_review(**kwargs))
    assert harness.decide_calls == 2  # transcribe + final; no repair re-decision
    section = report["routes"]["harness"]
    assert section["terminal_state"] == "PARTIAL"
    assert section["verification"]["passed"] is False
    event_types = [e.get("event_type") for e in section["events"]]
    assert event_types.count("model.request.started") == 2
    assert "verifier.completed" in event_types
    assert "repair.requested" not in event_types  # fail-fast: no verifier repair round
    assert report["review_completed"] is False


def test_pre_execution_frame_cap_blocks_oversized_sample(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    media = _FakeMedia(candidate_count=30)
    kwargs["media"] = media
    harness = _GreedyFrameProvider()  # requests 25 frames against a 24-frame budget
    kwargs["harness_client"] = harness
    report = asyncio.run(review.run_review(**kwargs))
    section = report["routes"]["harness"]
    assert section["terminal_state"] == "EXHAUSTED"
    assert "frame" in section["failure_reason"]
    assert media.frame_extract_calls == 0  # refused before any frame extraction
    assert section["frames"] == 0
    assert harness.decide_calls == 1


def test_pre_execution_frame_cap_is_cumulative(tmp_path: Path) -> None:
    kwargs = _run_kwargs(tmp_path)
    media = _FakeMedia(candidate_count=30)
    kwargs["media"] = media
    harness = _CumulativeFrameProvider()  # 20 frames fit; 12 more exceed the remaining 4
    kwargs["harness_client"] = harness
    report = asyncio.run(review.run_review(**kwargs))
    section = report["routes"]["harness"]
    assert section["terminal_state"] == "EXHAUSTED"
    assert media.frame_extract_calls == 1  # only the first, in-budget sample ran
    assert section["frames"] == 20
    assert harness.decide_calls == 2


def test_run_review_native_failure_keeps_provider_reported_usage(tmp_path: Path) -> None:
    error = NativeVideoError(
        "Native video stream did not complete successfully.",
        category="stream_error",
        request_bytes=2048,
        attempts=1,
    )
    error.usage = ProviderUsage(  # provider reported full usage before failing
        model_calls=1, input_bytes=2048, input_tokens=77, output_tokens=12, reported=True
    )
    kwargs = _run_kwargs(tmp_path)
    kwargs["native_client"] = _FakeNativeClient(error=error)
    report = asyncio.run(review.run_review(**kwargs))
    native = report["routes"]["native"]
    assert native["status"] == "failed"
    usage = native["usage"]
    assert usage["model_calls"] == 1
    assert usage["input_bytes"] == 2048
    assert usage["input_tokens"] == 77  # reported usage survives the failure
    assert usage["output_tokens"] == 12
    assert usage["reported"] is True
    assert "harness" not in report["routes"]
    events = [
        json.loads(line)
        for line in (tmp_path / "review_out" / "native" / "events.jsonl").read_text().splitlines()
    ]
    failed = [e for e in events if e.get("event_type") == "model.request.failed"]
    assert failed[0]["usage"]["input_tokens"] == 77  # kept in the trace too
    assert failed[0]["usage"]["provider_reported"] is True
    persisted = (tmp_path / "review_out" / "report.json").read_text(encoding="utf-8")
    assert '"input_tokens": 77' in persisted
