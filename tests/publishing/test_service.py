"""RED-first Batch 3D-2 tests: opt-in local publishing service and CLI.

These tests specify the publish service contract: strict local path boundaries,
one bounded PublishingPolicy run with exactly one model call and one
sample_evidence call, result_writer-driven export before bundle finalization,
content-safe results, and a CLI that prints only safe JSON metadata. They
import vidsnap.publishing.service and the CLI publish command, which do not
exist yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.publishing.test_policy import (
    ARTICLE_TEXT,
    SUMMARY_TEXT,
    FakePublishingFFmpeg,
    FakePublishingModel,
)
from vidsnap.config import HarnessConfig
from vidsnap.contracts import HarnessPolicy, TerminalState
from vidsnap.publishing.contracts import DeliverableKind, PublishingResult
from vidsnap.publishing.policy import PublishingPolicy
from vidsnap.publishing.service import (
    PublishServiceResult,
    audit_publishing_caps,
    publish_video,
)
from vidsnap.publishing.task import PublishingDraft, PublishingModelResponse

SECRET = "NONSECRET_TEST_MARKER_FIXED_LOCAL_KEY"
TRANSCRIPT = "完整的本地 transcript 第一句。\n第二句。"


def setup_inputs(tmp_path: Path, *, transcript: str = TRANSCRIPT) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    video = tmp_path / "video.mp4"
    video.write_bytes(b"deterministic-local-video-bytes")
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text(transcript, encoding="utf-8")
    return {
        "video": video,
        "transcript_path": transcript_path,
        "run_dir": tmp_path / "outside" / "run",
        "output_dir": tmp_path / "outside" / "publish",
        "repository_root": repository_root,
    }


async def run_service(tmp_path: Path, *, model=None, policy=None, **overrides):
    inputs = setup_inputs(tmp_path)
    inputs.update(overrides)
    return await publish_video(
        config=HarnessConfig(api_key=SECRET),
        media=FakePublishingFFmpeg(),
        model=model or FakePublishingModel(),
        policy=policy,
        **inputs,
    )


@pytest.mark.asyncio
async def test_success_path_one_model_call_one_sample_call_three_deliverables(tmp_path) -> None:
    model = FakePublishingModel()

    result = await run_service(tmp_path, model=model)

    assert isinstance(result, PublishServiceResult)
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.failure_reason is None
    assert model.draft_calls == 1
    assert model.observed_transcripts == [TRANSCRIPT]
    assert result.run_id
    assert (result.run_path / "manifest.json").is_file()
    assert_terminal_agreement(result.run_path, result)

    output_dir = tmp_path / "outside" / "publish"
    for filename in ("dialogue.md", "article.md", "summary.md"):
        assert (output_dir / filename).is_file()
    copied_images = sorted(path.name for path in (output_dir / "images").iterdir())
    assert copied_images == ["frame-001.jpg", "frame-002.jpg"]
    article_text = (output_dir / "article.md").read_text(encoding="utf-8")
    assert "![00:00:00](images/frame-001.jpg)" in article_text
    assert "![00:00:01](images/frame-002.jpg)" in article_text
    article_reference = next(
        item for item in result.publishing.deliverables if item.kind is DeliverableKind.ARTICLE
    )
    assert [ref.path for ref in article_reference.image_references] == [
        Path("images/frame-001.jpg"),
        Path("images/frame-002.jpg"),
    ]
    for reference in article_reference.image_references:
        copied = output_dir / reference.path
        assert copied.is_file()
        assert reference.byte_count == copied.stat().st_size
    assert isinstance(result.publishing, PublishingResult)
    assert {item.kind for item in result.publishing.deliverables} == set(DeliverableKind)
    assert result.verification is not None
    assert result.verification.passed is True

    events = [
        json.loads(line)
        for line in (result.run_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    completed_phases = [
        event["phase"] for event in events if event.get("event_type") == "phase.completed"
    ]
    assert completed_phases.count("sample_evidence") == 1


@pytest.mark.asyncio
async def test_result_and_bundle_never_leak_private_content(tmp_path) -> None:
    result = await run_service(tmp_path)

    as_json = json.dumps(result.publishing.model_dump(mode="json"), ensure_ascii=False)
    assert TRANSCRIPT not in as_json
    assert ARTICLE_TEXT not in as_json
    assert SUMMARY_TEXT not in as_json
    assert SECRET not in as_json

    bundle_text = ""
    for path in sorted(result.run_path.rglob("*")):
        if path.is_file() and "artifacts" not in path.relative_to(result.run_path).parts:
            bundle_text += path.read_text(encoding="utf-8")
    assert TRANSCRIPT not in bundle_text
    assert ARTICLE_TEXT not in bundle_text
    assert SUMMARY_TEXT not in bundle_text
    assert SECRET not in bundle_text
    assert not (result.run_path / "result.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    ["run_dir", "output_dir"],
)
async def test_directories_must_be_absolute_distinct_and_outside_repository(
    tmp_path, override
) -> None:
    inputs = setup_inputs(tmp_path)

    relative = dict(inputs)
    relative[override] = Path("relative/dir")
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **relative,
        )

    same = dict(inputs)
    same["run_dir"] = inputs["output_dir"]
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **same,
        )

    inside_repo = dict(inputs)
    inside_repo[override] = inputs["repository_root"] / "leak"
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **inside_repo,
        )


@pytest.mark.asyncio
async def test_dot_dot_paths_are_canonicalized_before_rejection(tmp_path) -> None:
    """run_dir with a dot-dot detour that canonicalizes onto output_dir must fail."""
    inputs = setup_inputs(tmp_path)
    dotted = dict(inputs)
    dotted["run_dir"] = tmp_path / "outside" / "detour" / ".." / "publish"

    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **dotted,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("nesting", ["output-inside-run", "run-inside-output"])
async def test_nested_run_and_output_dirs_are_rejected(tmp_path, nesting) -> None:
    """One directory strictly inside the other overlaps and must be rejected."""
    inputs = setup_inputs(tmp_path)
    nested = dict(inputs)
    if nesting == "output-inside-run":
        nested["run_dir"] = tmp_path / "outside" / "run"
        nested["output_dir"] = tmp_path / "outside" / "run" / "publish"
    else:
        nested["output_dir"] = tmp_path / "outside" / "publish"
        nested["run_dir"] = tmp_path / "outside" / "publish" / "run"

    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **nested,
        )
    assert not (tmp_path / "outside" / "run").exists()
    assert not (tmp_path / "outside" / "publish").exists()


@pytest.mark.asyncio
async def test_symlinked_run_dir_escaping_into_repository_is_rejected(tmp_path) -> None:
    """A run_dir symlink that resolves inside the repository must be rejected."""
    inputs = setup_inputs(tmp_path)
    inside = inputs["repository_root"] / "smuggled"
    inside.mkdir()
    link = tmp_path / "run-link"
    link.symlink_to(inside)
    escaped = dict(inputs)
    escaped["run_dir"] = link

    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **escaped,
        )
    assert not (inside / "manifest.json").exists()


@pytest.mark.asyncio
async def test_inputs_must_be_existing_files_and_transcript_non_blank(tmp_path) -> None:
    inputs = setup_inputs(tmp_path)

    missing_video = dict(inputs)
    missing_video["video"] = tmp_path / "absent.mp4"
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **missing_video,
        )

    missing_transcript = dict(inputs)
    missing_transcript["transcript_path"] = tmp_path / "absent.txt"
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **missing_transcript,
        )

    blank = dict(inputs)
    blank_transcript = tmp_path / "blank.txt"
    blank_transcript.write_text("  \n\t ", encoding="utf-8")
    blank["transcript_path"] = blank_transcript
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **blank,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["video", "transcript_path"])
async def test_input_files_must_be_absolute_and_outside_repository(tmp_path, field) -> None:
    inputs = setup_inputs(tmp_path)

    relative = dict(inputs)
    relative[field] = Path("relative-input.bin")
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **relative,
        )

    inside_repo = dict(inputs)
    smuggled = inputs["repository_root"] / ("smuggled.mp4" if field == "video" else "smuggled.txt")
    smuggled.write_bytes(b"smuggled-bytes")
    inside_repo[field] = smuggled
    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **inside_repo,
        )

    assert not inputs["run_dir"].exists(), "no files may be created before validation"
    assert not (tmp_path / "outside" / "publish").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["video", "transcript_path"])
async def test_input_file_symlinks_into_repository_are_rejected(tmp_path, field) -> None:
    inputs = setup_inputs(tmp_path)
    smuggled = inputs["repository_root"] / ("smuggled.mp4" if field == "video" else "smuggled.txt")
    smuggled.write_bytes(b"smuggled-bytes")
    link = tmp_path / ("video-link.mp4" if field == "video" else "transcript-link.txt")
    link.symlink_to(smuggled)
    escaped = dict(inputs)
    escaped[field] = link

    with pytest.raises(ValueError):
        await publish_video(
            config=HarnessConfig(api_key=SECRET),
            media=FakePublishingFFmpeg(),
            model=FakePublishingModel(),
            **escaped,
        )
    assert not inputs["run_dir"].exists()


class RecordingPublishingFFmpeg(FakePublishingFFmpeg):
    """FFmpeg double that records every source path handed to probe."""

    def __init__(self) -> None:
        super().__init__()
        self.probed_sources: list[Path] = []

    async def probe(self, source: Path):
        self.probed_sources.append(source)
        return await super().probe(source)


@pytest.mark.asyncio
async def test_outside_video_symlink_is_resolved_before_reaching_media(tmp_path) -> None:
    inputs = setup_inputs(tmp_path)
    link = tmp_path / "video-link.mp4"
    link.symlink_to(inputs["video"])
    media = RecordingPublishingFFmpeg()

    result = await publish_video(
        config=HarnessConfig(api_key=SECRET),
        media=media,
        model=FakePublishingModel(),
        **{**inputs, "video": link},
    )

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert media.probed_sources == [inputs["video"].resolve()]


def test_audit_publishing_caps_accepts_exactly_one_tool_one_model_twelve_frames() -> None:
    assert audit_publishing_caps(tool_calls=1, model_calls=1, evidence_frames=12) is None
    assert audit_publishing_caps(tool_calls=1, model_calls=1, evidence_frames=3) is None


def test_audit_publishing_caps_rejects_every_overshoot() -> None:
    for kwargs in (
        {"tool_calls": 2, "model_calls": 1, "evidence_frames": 3},
        {"tool_calls": 0, "model_calls": 1, "evidence_frames": 3},
        {"tool_calls": 1, "model_calls": 2, "evidence_frames": 3},
        {"tool_calls": 1, "model_calls": 0, "evidence_frames": 3},
        {"tool_calls": 1, "model_calls": 1, "evidence_frames": 13},
    ):
        reason = audit_publishing_caps(**kwargs)  # type: ignore[arg-type]
        assert reason, f"expected a cap violation for {kwargs}"


class DoubleSamplePolicy(PublishingPolicy):
    """Rogue policy double that attempts a second sample_evidence tool call."""

    async def execute(self, context, kernel) -> None:
        await kernel.run_probe(context)
        await kernel.run_tool(context, "sample_evidence", {"max_frames": 12})
        await kernel.run_tool(context, "sample_evidence", {"max_frames": 4})
        await kernel.synthesize(context)
        verification = kernel.verify(context)
        context.terminal_state = (
            TerminalState.SUCCEEDED if verification.passed else TerminalState.PARTIAL
        )


class DoubleSynthesisPolicy(PublishingPolicy):
    """Rogue policy double that attempts a second qwen3.8-max model call."""

    async def execute(self, context, kernel) -> None:
        await kernel.run_probe(context)
        await kernel.run_tool(context, "sample_evidence", {"max_frames": 12})
        await kernel.synthesize(context)
        await kernel.synthesize(context)
        verification = kernel.verify(context)
        context.terminal_state = (
            TerminalState.SUCCEEDED if verification.passed else TerminalState.PARTIAL
        )


class CounterTamperingPolicy(PublishingPolicy):
    """Rogue policy double that tampers with kernel counters after a canonical run."""

    async def execute(self, context, kernel) -> None:
        await super().execute(context, kernel)
        context.tool_calls += 1


def assert_terminal_agreement(run_path: Path, result) -> None:
    """The returned state, manifest, and terminal event must all tell one truth."""
    manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (run_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    terminal_events = [
        event
        for event in events
        if event.get("event_type") == "phase.completed" and event.get("phase") == "terminal"
    ]
    assert terminal_events, "expected one completed terminal phase event"
    expected = result.terminal_state.value
    assert manifest["terminal_state"] == expected
    assert terminal_events[-1]["payload"]["terminal_state"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy_factory", "expected_reason"),
    [
        (lambda: DoubleSamplePolicy(), "tool-call budget exceeded"),
        (lambda: DoubleSynthesisPolicy(), "model-call budget exceeded"),
    ],
)
async def test_second_budget_attempt_ends_truthfully_exhausted_without_export(
    tmp_path, policy_factory, expected_reason
) -> None:
    result = await run_service(tmp_path, policy=policy_factory())

    assert result.terminal_state is TerminalState.EXHAUSTED
    assert result.failure_reason == expected_reason
    assert result.publishing is None
    assert not (tmp_path / "outside" / "publish").exists()
    assert_terminal_agreement(result.run_path, result)


@pytest.mark.asyncio
async def test_counter_tampering_ends_failed_without_export(tmp_path) -> None:
    result = await run_service(tmp_path, policy=CounterTamperingPolicy())

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason
    assert TRANSCRIPT not in result.failure_reason
    assert result.publishing is None
    assert not (tmp_path / "outside" / "publish").exists()
    assert_terminal_agreement(result.run_path, result)


def test_global_harness_policy_defaults_stay_untouched_by_publishing() -> None:
    defaults = HarnessPolicy()
    assert defaults.max_tool_calls == 6
    assert defaults.max_model_calls == 12
    assert defaults.max_evidence_frames == 96


class FailingPublishingModel(FakePublishingModel):
    """Publishing model double whose single call raises a redacted provider error."""

    async def draft_deliverables(self, evidence, transcript, probe):
        from vidsnap.providers.base import ProviderError

        raise ProviderError("Qwen publishing-draft request failed")


@pytest.mark.asyncio
async def test_model_failure_terminates_failed_without_partial_output(tmp_path) -> None:
    result = await run_service(tmp_path, model=FailingPublishingModel())

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason
    assert result.publishing is None
    assert not (tmp_path / "outside" / "publish").exists()


@pytest.mark.asyncio
async def test_verification_failure_publishes_nothing(tmp_path) -> None:
    class UnverifiedModel(FakePublishingModel):
        async def draft_deliverables(self, evidence, transcript, probe):
            self.draft_calls += 1
            draft = PublishingDraft(
                article=ARTICLE_TEXT + "\n\n[[image:frame-999]]",
                summary=SUMMARY_TEXT,
                image_evidence_ids=("frame-999",),
            )
            return PublishingModelResponse(draft=draft, usage_reported=False)

    result = await run_service(tmp_path, model=UnverifiedModel())

    assert result.terminal_state is TerminalState.PARTIAL
    assert result.publishing is None
    assert result.verification is not None
    assert result.verification.passed is False
    assert not (tmp_path / "outside" / "publish").exists()


@pytest.mark.asyncio
async def test_export_failure_terminates_failed_without_partial_files(tmp_path) -> None:
    inputs = setup_inputs(tmp_path)
    output_dir = inputs["output_dir"]
    output_dir.mkdir(parents=True)
    (output_dir / "preexisting.txt").write_text("user data", encoding="utf-8")

    result = await publish_video(
        config=HarnessConfig(api_key=SECRET),
        media=FakePublishingFFmpeg(),
        model=FakePublishingModel(),
        **inputs,
    )

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason
    assert result.publishing is None
    assert not (output_dir / "dialogue.md").exists()
    assert not (output_dir / "article.md").exists()
    assert not (output_dir / "summary.md").exists()
    assert (output_dir / "preexisting.txt").is_file(), "user data must never be deleted"


def test_cli_publish_outputs_safe_json_and_exit_codes(tmp_path, monkeypatch) -> None:
    transcript_content = "CLI transcript that must never be printed."

    async def fake_publish_video(**kwargs):
        del kwargs
        return PublishServiceResult(
            terminal_state=TerminalState.SUCCEEDED,
            run_path=tmp_path / "run",
            run_id="run-123",
            publishing=PublishingResult.model_validate(
                {
                    "run_id": "run-123",
                    "generated_at": "2026-08-24T12:00:00Z",
                    "deliverables": [
                        {
                            "kind": "dialogue",
                            "path": str(tmp_path / "out" / "dialogue.md"),
                            "sha256": "a" * 64,
                            "byte_count": 10,
                        },
                        {
                            "kind": "article",
                            "path": str(tmp_path / "out" / "article.md"),
                            "sha256": "b" * 64,
                            "byte_count": 20,
                        },
                        {
                            "kind": "summary",
                            "path": str(tmp_path / "out" / "summary.md"),
                            "sha256": "c" * 64,
                            "byte_count": 30,
                        },
                    ],
                }
            ),
            verification=None,
            failure_reason=None,
        )

    monkeypatch.setattr("vidsnap.cli.publish_video", fake_publish_video)
    from vidsnap.cli import app

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text(transcript_content, encoding="utf-8")
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", SECRET)

    runner = CliRunner()
    success = runner.invoke(
        app,
        [
            "publish",
            "--video",
            str(video),
            "--transcript",
            str(transcript_path),
            "--run-dir",
            str(tmp_path / "run"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert success.exit_code == 0, success.output
    payload = json.loads(success.output)
    assert payload["terminal_state"] == "SUCCEEDED"
    assert payload["run_id"] == "run-123"
    assert len(payload["deliverables"]) == 3
    for forbidden in (transcript_content, SECRET, "Authorization", "Bearer"):
        assert forbidden not in success.output

    failed = runner.invoke(
        app,
        [
            "publish",
            "--video",
            "relative-video.mp4",
            "--transcript",
            str(transcript_path),
            "--run-dir",
            str(tmp_path / "run2"),
            "--output-dir",
            str(tmp_path / "out2"),
        ],
    )
    assert failed.exit_code != 0


@pytest.mark.parametrize(
    ("error", "forbidden"),
    [
        (
            RuntimeError("boom api_key=NONSECRET_TEST_MARKER_LEAK transcript=hidden-content"),
            ("boom", "NONSECRET_TEST_MARKER_LEAK", "hidden-content", "Traceback"),
        ),
        (KeyError("NONSECRET_TEST_MARKER_LEAK"), ("NONSECRET_TEST_MARKER_LEAK", "Traceback")),
        (OSError("disk failure at /secret/mount"), ("Traceback",)),
    ],
)
def test_cli_publish_maps_unexpected_errors_to_safe_nonzero_exit(
    tmp_path, monkeypatch, error, forbidden
) -> None:
    async def exploding(**kwargs):
        del kwargs
        raise error

    monkeypatch.setattr("vidsnap.cli.publish_video", exploding)
    from vidsnap.cli import app

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("safe transcript", encoding="utf-8")

    runner = CliRunner()
    failed = runner.invoke(
        app,
        [
            "publish",
            "--video",
            str(video),
            "--transcript",
            str(transcript_path),
            "--run-dir",
            str(tmp_path / "run"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert failed.exit_code == 1, failed.output
    for fragment in forbidden:
        assert fragment not in failed.output
    assert failed.output.strip().startswith("publish failed")


@pytest.mark.parametrize(
    "message",
    [
        ValueError("run_dir must be an absolute path"),
        FileExistsError("output directory must be empty or absent: /tmp/x"),
    ],
)
def test_cli_publish_reports_validation_failures_without_traceback(
    tmp_path, monkeypatch, message
) -> None:
    async def refusing(**kwargs):
        del kwargs
        raise message

    monkeypatch.setattr("vidsnap.cli.publish_video", refusing)
    from vidsnap.cli import app

    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("safe transcript", encoding="utf-8")

    runner = CliRunner()
    failed = runner.invoke(
        app,
        [
            "publish",
            "--video",
            str(video),
            "--transcript",
            str(transcript_path),
            "--run-dir",
            str(tmp_path / "run"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert failed.exit_code == 1, failed.output
    assert "Traceback" not in failed.output
    assert str(message) in failed.output
