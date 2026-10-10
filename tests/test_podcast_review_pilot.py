"""Offline tests for the podcast review pilot — no live model calls, no network."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from vidsnap.contracts import HarnessPolicy, VideoGoal, VideoSource
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.loopspec import default_loop_spec
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.runtime.context import RunContext
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.probe import MediaProbe
from vidsnap.video.sampling import AdaptiveSampler

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "podcast_review_pilot.py"

spec = importlib.util.spec_from_file_location("podcast_review_pilot", SCRIPT)
pilot = importlib.util.module_from_spec(spec)
sys.modules["podcast_review_pilot"] = pilot
spec.loader.exec_module(pilot)

PROBE_80S = MediaProbe(duration_seconds=80.0, fps=24.0, width=1280, height=720, has_audio=True)


class _FakeMedia:
    """Fake FFmpegPort: only probe is implemented; everything else must not be called."""

    def __init__(self, probe: MediaProbe | None = None, error: Exception | None = None) -> None:
        self._probe = probe
        self._error = error
        self.probe_calls = 0

    async def probe(self, source: Path) -> MediaProbe:
        self.probe_calls += 1
        if self._error is not None:
            raise self._error
        assert self._probe is not None
        return self._probe


@pytest.fixture()
def video(tmp_path: Path) -> Path:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00\x01\x02\x03" * 512)
    return clip


@pytest.fixture()
def transcript(tmp_path: Path) -> Path:
    path = tmp_path / "subtitles.txt"
    path.write_text(
        "\n".join(
            [
                "[00:04:30] 片头前的内容，不在窗口内",
                "不是时间戳行，应被跳过",
                '[00:04:40] 主持人：欢迎收听本期节目，今天我们讨论"联邦学习"',
                "[00:05:00] 嘉宾：联邦学习可以在不共享原始数据的前提下训练模型",
                "[00:05:20] 主持人：能举一个医疗领域的具体例子吗？",
                "[00:06:00] 窗口外内容，不应被选入",
                "[00:07:00] 同样窗口外",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_parse_transcript_selects_window_and_shifts_to_clip_time(transcript: Path) -> None:
    entries = pilot.parse_transcript(transcript, source_offset=280, duration=80.0)
    assert len(entries) == 3
    assert [e.start_seconds for e in entries] == [0.0, 20.0, 40.0]
    assert entries[0].end_seconds == 20.0
    assert entries[1].end_seconds == 40.0
    assert entries[2].end_seconds == 80.0  # clamped to clip end, next line at 360 is window edge
    assert entries[0].text.startswith("主持人：欢迎收听")
    assert '"联邦学习"' in entries[0].text


def test_validate_clip_metadata_bounds() -> None:
    pilot.validate_clip_metadata(PROBE_80S)
    pilot.validate_clip_metadata(
        MediaProbe(duration_seconds=120.0, fps=24.0, width=640, height=360, has_audio=False)
    )
    with pytest.raises(ValueError):
        pilot.validate_clip_metadata(
            MediaProbe(duration_seconds=121.0, fps=24.0, width=640, height=360, has_audio=True)
        )
    with pytest.raises(ValueError):
        pilot.validate_clip_metadata(
            MediaProbe(duration_seconds=0.0, fps=24.0, width=640, height=360, has_audio=False)
        )


def test_validate_only_probes_video_and_creates_no_output(
    video: Path, transcript: Path, tmp_path: Path
) -> None:
    media = _FakeMedia(probe=PROBE_80S)
    before = set(tmp_path.iterdir())
    summary = asyncio.run(
        pilot.validate_only(
            video=video,
            transcript=transcript,
            source_offset=280,
            output=tmp_path / "pilot_out",
            media=media,
        )
    )
    assert media.probe_calls == 1
    assert summary["clip"]["duration_seconds"] == 80.0
    assert summary["clip"]["max_frames_at_fps2"] == 160
    assert summary["transcript_entries"] == 3
    assert summary["source_digest"] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert set(tmp_path.iterdir()) == before  # validate-only must not occupy output


def test_validate_only_fails_on_unreadable_video(
    video: Path, transcript: Path, tmp_path: Path
) -> None:
    media = _FakeMedia(error=RuntimeError("ffprobe failed"))
    before = set(tmp_path.iterdir())
    with pytest.raises(Exception):
        asyncio.run(
            pilot.validate_only(
                video=video,
                transcript=transcript,
                source_offset=280,
                output=tmp_path / "pilot_out",
                media=media,
            )
        )
    assert set(tmp_path.iterdir()) == before


def test_subprocess_validate_only_rejects_invalid_video(tmp_path: Path) -> None:
    bad_video = tmp_path / "garbage.mp4"
    bad_video.write_bytes(b"\x00" * 256)
    out_dir = tmp_path / "pilot_out"
    env = {"PATH": "", "PYTHONPATH": str(REPO_ROOT / "src")}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--video",
            str(bad_video),
            "--transcript",
            str(bad_video),  # exists but not timestamps; probe must fail first
            "--source-offset",
            "280",
            "--output",
            str(out_dir),
            "--validate-only",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert not out_dir.exists()
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined
    assert "Bearer" not in combined


def _make_context(tmp_path: Path, name: str) -> RunContext:
    bundle = RunBundle.create(
        tmp_path / name,
        loop_spec=default_loop_spec(),
        provider_url="https://example.invalid",
    )
    return RunContext(
        source=VideoSource(path=tmp_path / "clip.mp4"),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(VideoGoal(objective="测试")),
        task_model=object(),
        media=_FakeMedia(probe=PROBE_80S),
        sampler=AdaptiveSampler(),
    )


def test_preinjected_transcript_evidence_identical_in_both_contexts(
    transcript: Path, tmp_path: Path
) -> None:
    entries = pilot.parse_transcript(transcript, source_offset=280, duration=80.0)
    ctx_direct = _make_context(tmp_path, "direct")
    ctx_agentic = _make_context(tmp_path, "agentic")
    ids_direct = pilot.preinject_transcript(ctx_direct, entries)
    ids_agentic = pilot.preinject_transcript(ctx_agentic, entries)
    assert ids_direct and ids_direct == ids_agentic
    snap_direct = [
        (e.id, e.start_seconds, e.end_seconds, e.modality, e.content) for e in ctx_direct.evidence
    ]
    snap_agentic = [
        (e.id, e.start_seconds, e.end_seconds, e.modality, e.content) for e in ctx_agentic.evidence
    ]
    assert snap_direct == snap_agentic
    assert len(snap_direct) == len(entries) > 0
    assert all(item[3] == "transcript" for item in snap_direct)


def test_usage_summary_never_writes_unknown_as_zero() -> None:
    unreported = ProviderUsage(model_calls=1, input_bytes=441, reported=False)
    summary = pilot.usage_summary(unreported)
    assert summary["input_tokens"] is None
    assert summary["output_tokens"] is None
    assert summary["input_bytes"] == 441  # locally measured, real even when unreported
    assert summary["model_calls"] == 1
    assert summary["reported"] is False
    empty = pilot.usage_summary(None)
    assert empty["input_tokens"] is None
    assert empty["input_bytes"] is None
    assert empty["model_calls"] is None
    reported = ProviderUsage(
        model_calls=2, input_bytes=900, input_tokens=12, output_tokens=7, reported=True
    )
    assert pilot.usage_summary(reported)["input_tokens"] == 12


def test_render_report_escapes_xss_and_marks_synthetic() -> None:
    report = {
        "synthetic": True,
        "goal": "测试目标",
        "source": {"digest": "ab" * 32, "offset_seconds": 280, "clip_duration": 80.0},
        "evidence": [
            {
                "id": "transcript-001",
                "start_seconds": 0.0,
                "end_seconds": 20.0,
                "content": "<script>alert(1)</script><img src=x onerror=alert(1)>主持人",
            }
        ],
        "variants": {
            "direct": {
                "terminal_state": "SUCCEEDED",
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "input_bytes": 441,
                    "model_calls": 1,
                    "reported": False,
                },
                "output": {"summary": "包含<script>的摘要", "claims": []},
                "events": [
                    {
                        "sequence": 1,
                        "event_type": "synthesize_result.completed",
                        "status": "completed",
                        "duration_ms": 123,
                        "payload": {"bytes": 441},
                    },
                ],
            },
        },
    }
    page = pilot.render_report(report, clip_name="clip.mp4")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page  # content preserved, escaped
    assert "&lt;img src=x onerror=alert(1)&gt;" in page  # escaped text may remain
    assert "<img src=x" not in page  # but never as a live tag
    assert "synthetic" in page.lower()
    assert "unknown" in page  # unreported tokens rendered as unknown
    assert "sk-" not in page and "Bearer" not in page and "Authorization" not in page


def test_ensure_output_dir_rejects_nonempty_and_repo_internal(tmp_path: Path) -> None:
    target = tmp_path / "fresh"
    pilot.ensure_output_dir(target, repo_root=REPO_ROOT)  # missing dir is fine, not created
    assert not target.exists()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("do not touch")
    with pytest.raises(ValueError):
        pilot.ensure_output_dir(occupied, repo_root=REPO_ROOT)
    assert (occupied / "keep.txt").read_text() == "do not touch"
    with pytest.raises(ValueError):
        pilot.ensure_output_dir(REPO_ROOT / "pilot_out_should_fail", repo_root=REPO_ROOT)


class _FakePilotMedia:
    """FFmpegPort fake: real probe metadata, tiny real frame files, no ffmpeg."""

    def __init__(self) -> None:
        from vidsnap.video.sampling import AdaptiveSampler as _AS

        self.sampler = _AS()

    async def probe(self, source: Path) -> MediaProbe:
        return PROBE_80S

    async def visual_candidates(self, source, probe):
        return []

    async def extract_frames(self, source, candidates, output_dir):
        return []

    async def extract_timeline_frames(self, source, *, fps, output_dir):
        from vidsnap.video.probe import ExtractedFrame

        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index in range(3):
            frame_path = output_dir / f"frame-{index:03d}.jpg"
            frame_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=float(index) * 30.0,
                    perceptual_hash=f"hash{index}",
                )
            )
        return frames

    async def extract_audio(self, source, output_path, *, start_seconds=0.0, end_seconds=None):
        raise AssertionError("ASR is unavailable in this pilot; extract_audio must not run")

    async def scene_timestamps(self, source):
        return []


_RESULT_PAYLOAD = {
    "summary": "离线假模型摘要",
    "claims": [
        {
            "text": "主持人讨论了联邦学习",
            "evidence": [{"evidence_id": "transcript-001"}],
        }
    ],
}


class _FakePilotProvider:
    """Provider fake: counts calls, never touches the network, returns strict results."""

    def __init__(self, output: dict | None = None) -> None:
        from vidsnap.providers.base import ProviderIdentity

        self.identity = ProviderIdentity(
            id="qwen", model="qwen3.8-max", base_url="https://example.invalid"
        )
        self.analyze_calls = 0
        self.decide_calls = 0
        self._output = output if output is not None else _RESULT_PAYLOAD

    async def analyze_evidence(self, evidence, goal):
        from vidsnap.contracts import VideoAnalysisResult
        from vidsnap.providers.base import ModelResponse

        self.analyze_calls += 1
        return ModelResponse(
            result=VideoAnalysisResult.model_validate(self._output),
            input_tokens=10,
            output_tokens=5,
            input_bytes=1234,
            usage_reported=True,
        )

    async def decide_next(self, request):
        from vidsnap.contracts.agent import AgentDecision
        from vidsnap.providers.base import AgentDecisionResponse

        self.decide_calls += 1
        decision = AgentDecision.model_validate({"kind": "final", "output": self._output})
        return AgentDecisionResponse(
            decision=decision,
            usage=ProviderUsage(model_calls=1, input_bytes=4321, reported=False),
        )


def test_run_latency_uses_terminal_duration_not_offset_sum() -> None:
    events = [
        {"event_type": "run.started", "status": "started", "monotonic_offset_ms": 11},
        {
            "event_type": "phase.completed",
            "status": "completed",
            "monotonic_offset_ms": 111,
            "duration_ms": 100,
            "payload": {"terminal_state": "SUCCEEDED"},
        },
    ]
    assert pilot._run_latency_ms(events) == 100
    no_duration = [
        {"event_type": "run.started", "status": "started", "monotonic_offset_ms": 11},
        {
            "event_type": "phase.completed",
            "status": "completed",
            "monotonic_offset_ms": 111,
            "payload": {"terminal_state": "SUCCEEDED"},
        },
    ]
    assert pilot._run_latency_ms(no_duration) == 100
    assert pilot._run_latency_ms([]) is None


def test_render_report_evidence_rows_are_scoped_per_variant() -> None:
    report = {
        "synthetic": True,
        "goal": "测试目标",
        "source": {"digest": "ab" * 32, "offset_seconds": 280, "clip_duration": 80.0},
        "evidence": [],
        "variants": {
            "direct": {
                "terminal_state": "SUCCEEDED",
                "usage": {},
                "events": [],
                "evidence": [
                    {
                        "id": "frame-001",
                        "start_seconds": 0,
                        "end_seconds": 0,
                        "modality": "frame",
                    }
                ],
                "output": {"summary": "s", "claims": []},
            },
            "agentic": {
                "terminal_state": "SUCCEEDED",
                "usage": {},
                "events": [],
                "evidence": [
                    {
                        "id": "frame-001",
                        "start_seconds": 35,
                        "end_seconds": 35,
                        "modality": "frame",
                    }
                ],
                "output": {"summary": "s", "claims": []},
            },
        },
    }
    page = pilot.render_report(report, clip_name="clip.mp4")
    assert "direct/frame-001" in page
    assert "agentic/frame-001" in page


def test_render_report_claim_seek_is_scoped_per_variant() -> None:
    report = {
        "synthetic": True,
        "goal": "测试目标",
        "source": {"digest": "ab" * 32, "offset_seconds": 280, "clip_duration": 80.0},
        "evidence": [],
        "variants": {
            "direct": {
                "terminal_state": "SUCCEEDED",
                "usage": {},
                "events": [],
                "evidence": [
                    {
                        "id": "frame-001",
                        "start_seconds": 0,
                        "end_seconds": 0,
                        "modality": "frame",
                    }
                ],
                "output": {
                    "summary": "s",
                    "claims": [{"text": "d", "evidence": [{"evidence_id": "frame-001"}]}],
                },
            },
            "agentic": {
                "terminal_state": "SUCCEEDED",
                "usage": {},
                "events": [],
                "evidence": [
                    {
                        "id": "frame-001",
                        "start_seconds": 35,
                        "end_seconds": 35,
                        "modality": "frame",
                    }
                ],
                "output": {
                    "summary": "s",
                    "claims": [{"text": "a", "evidence": [{"evidence_id": "frame-001"}]}],
                },
            },
        },
    }
    page = pilot.render_report(report, clip_name="clip.mp4")
    assert 'data-seek="0"' in page
    assert 'data-seek="35"' in page


def test_run_pilot_offline_end_to_end_with_real_kernels(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x01\x02\x03" * 512)
    transcript = tmp_path / "subtitles.txt"
    transcript.write_text(
        "[00:04:40] 主持人：欢迎收听本期节目\n[00:05:00] 嘉宾：讨论联邦学习\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "pilot_out"
    provider = _FakePilotProvider()
    report = asyncio.run(
        pilot.run_pilot(
            video=video,
            transcript=transcript,
            source_offset=280,
            output_dir=output_dir,
            client=provider,
            media=_FakePilotMedia(),
        )
    )
    assert provider.analyze_calls == 1  # Direct: exactly one model call
    assert provider.decide_calls == 1  # Agentic: final answer in one decision
    direct = report["variants"]["direct"]
    agentic = report["variants"]["agentic"]
    assert direct["terminal_state"] == "SUCCEEDED"
    assert agentic["terminal_state"] == "SUCCEEDED"
    assert direct["usage"]["input_bytes"] == 1234
    assert direct["usage"]["input_tokens"] == 10
    assert direct["usage"]["output_tokens"] == 5
    assert direct["usage"]["model_calls"] == 1
    assert direct["usage"]["reported"] is True
    assert agentic["usage"]["input_bytes"] == 4321
    assert agentic["usage"]["input_tokens"] is None
    assert agentic["usage"]["output_tokens"] is None
    assert agentic["usage"]["reported"] is False
    assert direct["run_path"] == "direct"
    assert agentic["run_path"] == "agentic"
    assert direct["verification"]["gates"]["schema_valid"] is True
    assert Path(direct["run_path"]).name == "direct"
    assert (output_dir / "direct" / "manifest.json").is_file()
    assert (output_dir / "agentic" / "manifest.json").is_file()
    assert (output_dir / "report.json").is_file()
    html_page = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "离线假模型摘要" in html_page
    assert "未记录" in html_page or "call_review" in html_page
    assert (output_dir / "clip.mp4").read_bytes() == video.read_bytes()
    assert direct["events"] and agentic["events"]


def test_run_pilot_stops_after_partial_direct(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x01\x02\x03" * 512)
    transcript = tmp_path / "subtitles.txt"
    transcript.write_text(
        "[00:04:40] 主持人：欢迎收听本期节目\n[00:05:00] 嘉宾：讨论联邦学习\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "pilot_out"
    provider = _FakePilotProvider(output={"summary": "无claims结果", "claims": []})
    report = asyncio.run(
        pilot.run_pilot(
            video=video,
            transcript=transcript,
            source_offset=280,
            output_dir=output_dir,
            client=provider,
            media=_FakePilotMedia(),
        )
    )
    assert provider.analyze_calls == 1
    assert provider.decide_calls == 0  # Agentic never ran
    assert report["variants"]["direct"]["terminal_state"] == "PARTIAL"
    assert "agentic" not in report["variants"]
    assert (output_dir / "report.json").is_file()
