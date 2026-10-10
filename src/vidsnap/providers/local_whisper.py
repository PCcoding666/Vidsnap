"""Local cached Whisper transcription behind the TranscriptionPort boundary."""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import time
import wave
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vidsnap.contracts.agent import ProviderUsage
from vidsnap.plugins.base import TranscriptionResponse
from vidsnap.providers.base import ProviderError


class LocalWhisperError(ProviderError):
    """Safe local-ASR failure; never echoes child output or environment."""


@dataclass(frozen=True, slots=True)
class LocalWhisperExecution:
    """Measured facts of one real local ASR execution; no remote usage exists."""

    model_path: Path
    audio_bytes: int
    audio_seconds: float
    duration_seconds: float
    status: str
    attempted: bool
    started: bool
    returncode: int | None


class RunnerSpawnError(Exception):
    """The Whisper process could not be started at all."""


class RunnerTimeoutError(asyncio.TimeoutError):
    """Timeout after spawn; carries the reaped exit code when known."""

    def __init__(self, returncode: int | None = None) -> None:
        super().__init__()
        self.returncode = returncode


class RunnerCancelledError(asyncio.CancelledError):
    """Cancellation after spawn; carries the reaped exit code when known."""

    def __init__(self, returncode: int | None = None) -> None:
        super().__init__()
        self.returncode = returncode


class WhisperRunner(Protocol):
    """Process boundary for one bounded Whisper CLI invocation."""

    async def __call__(
        self,
        *,
        executable: Path,
        audio_path: Path,
        output_dir: Path,
        model_path: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> int:
        """Run Whisper once and return its exit code."""


def _scrubbed_env() -> dict[str, str]:
    """Minimal offline child environment with no inherited credentials."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C.UTF-8",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


async def _default_runner(
    *,
    executable: Path,
    audio_path: Path,
    output_dir: Path,
    model_path: Path,
    env: Mapping[str, str],
    timeout_seconds: float,
) -> int:
    try:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            "--model",
            str(model_path),
            "--device",
            "cpu",
            "--fp16",
            "False",
            "--threads",
            "4",
            "--language",
            "en",
            "--output_format",
            "txt",
            "--verbose",
            "False",
            "--output_dir",
            str(output_dir),
            str(audio_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=dict(env),
        )
    except OSError:
        raise RunnerSpawnError from None
    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RunnerTimeoutError(process.returncode) from None
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise RunnerCancelledError(process.returncode) from None


def _wav_duration_seconds(audio_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as handle:
            rate = handle.getframerate()
            frames = handle.getnframes()
            width = handle.getsampwidth()
            channels = handle.getnchannels()
            if rate <= 0:
                raise LocalWhisperError("Audio must be a valid WAV with a positive frame rate.")
            if frames <= 0 or width <= 0 or channels <= 0:
                raise LocalWhisperError("Audio must contain at least one PCM frame.")
            pcm = handle.readframes(frames)
            if len(pcm) != frames * width * channels:
                raise LocalWhisperError("Audio PCM data is truncated.")
            return frames / rate
    except (wave.Error, EOFError) as error:
        raise LocalWhisperError("Audio must be a valid WAV stream.") from error


class LocalWhisperTranscriber:
    """Transcribe bounded WAV bytes with a pinned, cached local Whisper model."""

    def __init__(
        self,
        *,
        executable: Path,
        model_path: Path,
        timeout_seconds: float = 120.0,
        runner: WhisperRunner | None = None,
        observer: Callable[[LocalWhisperExecution], None] | None = None,
    ) -> None:
        self._executable = Path(executable)
        self._model_path = Path(model_path)
        self._timeout_seconds = timeout_seconds
        self._runner: WhisperRunner = runner or _default_runner
        self._observer = observer

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        """Return transcript text from the CLI output file; failures stay failures."""
        if not self._model_path.is_file():
            raise LocalWhisperError("Cached Whisper model file is not available.")
        if mime_type != "audio/wav":
            raise LocalWhisperError("Only audio/wav input is supported by local Whisper.")
        audio_seconds = _wav_duration_seconds(audio_bytes)
        started_at = time.monotonic()
        status = "failed"
        attempted = False
        started = False
        returncode: int | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="vidsnap-whisper-") as temporary:
                work_dir = Path(temporary)
                audio_path = work_dir / "audio.wav"
                audio_path.write_bytes(audio_bytes)
                output_dir = work_dir / "out"
                output_dir.mkdir()
                attempted = True
                try:
                    returncode = await self._runner(
                        executable=self._executable,
                        audio_path=audio_path,
                        output_dir=output_dir,
                        model_path=self._model_path,
                        env=_scrubbed_env(),
                        timeout_seconds=self._timeout_seconds,
                    )
                    started = True
                except RunnerSpawnError:
                    raise LocalWhisperError("Local Whisper could not be started.") from None
                except RunnerTimeoutError as error:
                    started = True
                    returncode = error.returncode
                    raise LocalWhisperError("Local Whisper execution timed out.") from None
                except asyncio.TimeoutError:
                    raise LocalWhisperError("Local Whisper execution timed out.") from None
                except RunnerCancelledError as error:
                    started = True
                    returncode = error.returncode
                    raise
                except LocalWhisperError:
                    raise
                except Exception:
                    raise LocalWhisperError("Local Whisper execution failed.") from None
                if returncode != 0:
                    raise LocalWhisperError("Local Whisper exited with a failure status.")
                transcript_path = output_dir / f"{audio_path.stem}.txt"
                if not transcript_path.is_file():
                    raise LocalWhisperError("Local Whisper produced no transcript file.")
                text = transcript_path.read_text(encoding="utf-8").strip()
                if not text:
                    raise LocalWhisperError("Local Whisper produced an empty transcript file.")
                status = "completed"
                return TranscriptionResponse(
                    text=text,
                    usage=ProviderUsage(model_calls=0, reported=False),
                )
        finally:
            if self._observer is not None:
                self._observer(
                    LocalWhisperExecution(
                        model_path=self._model_path,
                        audio_bytes=len(audio_bytes),
                        audio_seconds=audio_seconds,
                        duration_seconds=time.monotonic() - started_at,
                        status=status,
                        attempted=attempted,
                        started=started,
                        returncode=returncode,
                    )
                )
