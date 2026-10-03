"""Fake-process boundary tests for the local cached Whisper transcription port."""

import asyncio
import io
import wave
from pathlib import Path
from typing import Any

import pytest

from vidsnap.providers.base import ProviderError
from vidsnap.providers.local_whisper import (
    LocalWhisperExecution,
    LocalWhisperTranscriber,
)


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x01" * 1600)
    return buffer.getvalue()


def _model_file(tmp_path: Path) -> Path:
    model_path = tmp_path / "whisper-model.bin"
    model_path.write_bytes(b"cached-model")
    return model_path


def _make_transcriber(
    tmp_path: Path,
    runner: Any,
    *,
    timeout_seconds: float = 30.0,
) -> tuple[LocalWhisperTranscriber, list[LocalWhisperExecution]]:
    executions: list[LocalWhisperExecution] = []
    transcriber = LocalWhisperTranscriber(
        executable=tmp_path / "whisper-cli",
        model_path=_model_file(tmp_path),
        timeout_seconds=timeout_seconds,
        runner=runner,
        observer=executions.append,
    )
    return transcriber, executions


def _write_transcript(kwargs: dict[str, Any], text: str = "ok") -> None:
    (kwargs["output_dir"] / f"{kwargs['audio_path'].stem}.txt").write_text(text, encoding="utf-8")


@pytest.mark.asyncio
async def test_transcript_comes_from_output_file_not_stdout(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        assert kwargs["audio_path"].read_bytes() == _wav_bytes()
        _write_transcript(kwargs, "  你好，世界  \n")
        return 0

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)

    response = await transcriber.transcribe(_wav_bytes())

    assert response.text == "你好，世界"
    assert response.usage.reported is False
    assert response.usage.model_calls == 0
    assert len(executions) == 1
    execution = executions[0]
    assert execution.status == "completed"
    assert execution.returncode == 0
    assert execution.duration_seconds >= 0
    assert execution.model_path == _model_file(tmp_path)
    assert execution.audio_bytes == len(_wav_bytes())
    assert abs(execution.audio_seconds - 0.1) < 1e-6


@pytest.mark.asyncio
async def test_nonzero_exit_is_failure_not_empty_success(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        return 1

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    assert [e.status for e in executions] == ["failed"]
    assert executions[0].returncode == 1


@pytest.mark.asyncio
async def test_zero_exit_without_transcript_file_is_failure(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        return 0

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    assert [e.status for e in executions] == ["failed"]


@pytest.mark.asyncio
async def test_invalid_audio_is_rejected_before_any_subprocess(tmp_path: Path) -> None:
    calls = 0

    async def fake_runner(**kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        return 0

    transcriber, _ = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(b"definitely not a wav")
    assert calls == 0


@pytest.mark.asyncio
async def test_missing_cached_model_path_blocks_without_download(tmp_path: Path) -> None:
    calls = 0

    async def fake_runner(**kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        return 0

    transcriber = LocalWhisperTranscriber(
        executable=tmp_path / "whisper-cli",
        model_path=tmp_path / "absent-model.bin",
        runner=fake_runner,
    )

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    assert calls == 0


@pytest.mark.asyncio
async def test_subprocess_receives_timeout_and_explicit_model_path(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    async def fake_runner(**kwargs: Any) -> int:
        captured.update(kwargs)
        _write_transcript(kwargs)
        return 0

    transcriber, _ = _make_transcriber(tmp_path, fake_runner, timeout_seconds=7.5)
    await transcriber.transcribe(_wav_bytes())

    assert captured["timeout_seconds"] == 7.5
    assert captured["model_path"] == _model_file(tmp_path)
    assert captured["executable"] == tmp_path / "whisper-cli"


@pytest.mark.asyncio
async def test_subprocess_timeout_is_failure(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        raise asyncio.TimeoutError

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    assert [e.status for e in executions] == ["failed"]


@pytest.mark.asyncio
async def test_child_environment_is_scrubbed_of_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-marker-qwen")
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", "test-marker-vidsnap")
    captured_env: dict[str, str] = {}

    async def fake_runner(**kwargs: Any) -> int:
        captured_env.update(kwargs["env"])
        _write_transcript(kwargs)
        return 0

    transcriber, _ = _make_transcriber(tmp_path, fake_runner)
    await transcriber.transcribe(_wav_bytes())

    assert "test-marker-qwen" not in captured_env.values()
    assert "test-marker-vidsnap" not in captured_env.values()
    assert not any(
        marker in key.upper()
        for key in captured_env
        for marker in ("API_KEY", "TOKEN", "SECRET", "CREDENTIAL")
    )


@pytest.mark.asyncio
async def test_failure_error_does_not_leak_child_output_or_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-marker-qwen")

    async def fake_runner(**kwargs: Any) -> int:
        raise RuntimeError("child stderr: traceback SECRET-MARKER-789")

    transcriber, _ = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError) as excinfo:
        await transcriber.transcribe(_wav_bytes())
    message = str(excinfo.value)
    assert "SECRET-MARKER-789" not in message
    assert "test-marker-qwen" not in message
    assert "traceback" not in message


@pytest.mark.asyncio
async def test_default_runner_invokes_whisper_cli_with_fixed_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, Any] = {}

    class FakeProcess:
        returncode = 0

        async def wait(self) -> int:
            argv = calls["argv"]
            output_dir = Path(argv[argv.index("--output_dir") + 1])
            (output_dir / "audio.txt").write_text("default runner text", encoding="utf-8")
            return 0

        def kill(self) -> None:
            raise AssertionError("no kill expected on the happy path")

    async def fake_exec(*argv: Any, **kwargs: Any) -> FakeProcess:
        calls["argv"] = list(argv)
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    transcriber = LocalWhisperTranscriber(
        executable=tmp_path / "whisper-cli",
        model_path=_model_file(tmp_path),
    )

    response = await transcriber.transcribe(_wav_bytes())

    assert response.text == "default runner text"
    argv = calls["argv"]
    assert argv[0] == str(tmp_path / "whisper-cli")

    def option_value(flag: str) -> str:
        return str(argv[argv.index(flag) + 1])

    assert option_value("--model") == str(_model_file(tmp_path))
    assert Path(option_value("--model")).is_absolute()
    assert option_value("--device") == "cpu"
    assert option_value("--fp16") == "False"
    assert option_value("--threads") == "4"
    assert option_value("--language") == "en"
    assert option_value("--output_format") == "txt"
    assert option_value("--verbose") == "False"
    assert argv[-1].endswith(".wav")
    env = calls["kwargs"]["env"]
    assert not any(
        marker in key.upper()
        for key in env
        for marker in ("API_KEY", "TOKEN", "SECRET", "CREDENTIAL")
    )


@pytest.mark.asyncio
async def test_default_runner_kills_and_reaps_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state: dict[str, Any] = {"killed": False, "wait_calls": 0}

    class HangingProcess:
        returncode = None

        async def wait(self) -> int:
            state["wait_calls"] += 1
            if not state["killed"]:
                await asyncio.sleep(60)
            self.returncode = -9
            return -9

        def kill(self) -> None:
            state["killed"] = True

    async def fake_exec(*argv: Any, **kwargs: Any) -> HangingProcess:
        return HangingProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    executions: list[LocalWhisperExecution] = []
    transcriber = LocalWhisperTranscriber(
        executable=tmp_path / "whisper-cli",
        model_path=_model_file(tmp_path),
        timeout_seconds=0.05,
        observer=executions.append,
    )

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    assert state["killed"] is True
    assert state["wait_calls"] == 2
    assert executions[0].attempted is True
    assert executions[0].started is True
    assert executions[0].returncode == -9


@pytest.mark.asyncio
async def test_default_runner_kills_and_reaps_on_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state: dict[str, Any] = {"killed": False, "wait_calls": 0, "reaped": False}

    class HangingProcess:
        returncode = None

        async def wait(self) -> int:
            state["wait_calls"] += 1
            if not state["killed"]:
                await asyncio.sleep(60)
            state["reaped"] = True
            self.returncode = -9
            return -9

        def kill(self) -> None:
            state["killed"] = True

    async def fake_exec(*argv: Any, **kwargs: Any) -> HangingProcess:
        return HangingProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    executions: list[LocalWhisperExecution] = []
    transcriber = LocalWhisperTranscriber(
        executable=tmp_path / "whisper-cli",
        model_path=_model_file(tmp_path),
        timeout_seconds=60.0,
        observer=executions.append,
    )

    task = asyncio.create_task(transcriber.transcribe(_wav_bytes()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state["killed"] is True
    assert state["reaped"] is True
    assert executions[0].attempted is True
    assert executions[0].started is True
    assert executions[0].returncode == -9


@pytest.mark.asyncio
async def test_wrapped_runner_failure_suppresses_underlying_cause(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        raise RuntimeError("child stderr SECRET-MARKER-789")

    transcriber, _ = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError) as excinfo:
        await transcriber.transcribe(_wav_bytes())
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


@pytest.mark.asyncio
async def test_timeout_failure_suppresses_underlying_cause(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        raise asyncio.TimeoutError

    transcriber, _ = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError) as excinfo:
        await transcriber.transcribe(_wav_bytes())
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def _empty_wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_truncated_wav_is_rejected_without_subprocess(tmp_path: Path) -> None:
    calls = 0

    async def fake_runner(**kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        return 0

    # The header still claims 1600 frames but the PCM payload is cut short.
    truncated = _wav_bytes()[:-100]
    transcriber, _ = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(truncated)
    assert calls == 0


@pytest.mark.asyncio
async def test_zero_frame_wav_is_rejected_without_subprocess(tmp_path: Path) -> None:
    calls = 0

    async def fake_runner(**kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        return 0

    transcriber, _ = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_empty_wav_bytes())
    assert calls == 0


@pytest.mark.asyncio
async def test_execution_marks_attempted_and_started_on_success(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        _write_transcript(kwargs)
        return 0

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)
    await transcriber.transcribe(_wav_bytes())

    execution = executions[0]
    assert execution.attempted is True
    assert execution.started is True
    assert execution.returncode == 0


@pytest.mark.asyncio
async def test_spawn_failure_is_attempted_but_not_started(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        raise OSError("exec format error")

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    execution = executions[0]
    assert execution.attempted is True
    assert execution.started is False
    assert execution.returncode is None


@pytest.mark.asyncio
async def test_unknown_runner_timeout_has_unknown_returncode(tmp_path: Path) -> None:
    async def fake_runner(**kwargs: Any) -> int:
        raise asyncio.TimeoutError

    transcriber, executions = _make_transcriber(tmp_path, fake_runner)

    with pytest.raises(ProviderError):
        await transcriber.transcribe(_wav_bytes())
    execution = executions[0]
    assert execution.attempted is True
    assert execution.returncode is None
