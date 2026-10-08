"""End to end: failing provider calls never leak credentials, headers, bodies, or URLs.

The real Qwen provider is driven through the CLI with an offline mocked
transport whose failures echo a dummy credential, the Authorization header, a
provider response body, a request id, and a signed URL. None of them may
appear in events.jsonl, manifest.json, index.jsonl, the command output, or
the exported HTML trace. No network is used.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from tests.recipes.test_interview_runner import FakeInterviewMedia, FakeInterviewTranscriber
from tests.runtime.fakes import FakeFFmpeg
from vidsnap.cli import app
from vidsnap.harness import VideoHarness
from vidsnap.providers.qwen import QwenProvider
from vidsnap.recipes import InterviewRecipeRunner

_CREDENTIAL = "vidsnap-leak-sentinel-credential-7c41"
_BODY = "SENTINEL-PROVIDER-BODY-5e2d"
_REQUEST_ID = "SENTINEL-REQUEST-ID-9b0a"
_SIGNATURE = "SENTINEL-SIGNATURE-31f6"
_SIGNED_URL = f"https://bucket.invalid/clip.mp4?Signature={_SIGNATURE}&Expires=1"
_NEEDLES = (_CREDENTIAL, "Bearer", _BODY, _REQUEST_ID, _SIGNATURE, "data_inspection_failed")

Handler = Callable[[httpx.Request], httpx.Response]


def _moderation_refusal(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(
        400,
        json={
            "error": {"code": "data_inspection_failed", "message": f"{_BODY} {_SIGNED_URL}"},
            "request_id": _REQUEST_ID,
        },
    )


def _auth_echo(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        401, text=f"rejected {request.headers.get('authorization')} {_BODY} {_SIGNED_URL}"
    )


def _connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError(
        f"cannot reach {request.url}?api_key={_CREDENTIAL} {_BODY} {_SIGNED_URL}",
        request=request,
    )


def _html_body(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(200, text=f"<html>{_BODY} {_SIGNED_URL} {_REQUEST_ID}</html>")


def _schema_invalid(request: httpx.Request) -> httpx.Response:
    del request
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps({"echo": _BODY, "u": _SIGNED_URL})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "id": _REQUEST_ID,
        },
    )


_SCENARIOS: dict[str, Handler] = {
    "moderation_400": _moderation_refusal,
    "auth_echo_401": _auth_echo,
    "connect_error": _connect_error,
    "html_200": _html_body,
    "schema_invalid_200": _schema_invalid,
}

# The exact failure each scenario must be recorded as, proving the transport was exercised.
_EXPECTED: dict[str, tuple[str, int | None]] = {
    "moderation_400": ("http_4xx", 400),
    "auth_echo_401": ("http_4xx", 401),
    "connect_error": ("connection_error", None),
    "html_200": ("invalid_response", None),
    "schema_invalid_200": ("invalid_response", None),
}


def _provider(handler: Handler) -> QwenProvider:
    return QwenProvider(api_key=_CREDENTIAL, transport=httpx.MockTransport(handler))


def _run_command(
    command: str, handler: Handler, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, Path, Path]:
    video = tmp_path / "input.mp4"
    video.write_bytes(b"deterministic-local-video-bytes")
    runs_root = tmp_path / "runs"
    if command == "analyze":
        monkeypatch.setattr(
            "vidsnap.cli.VideoHarness",
            lambda: VideoHarness(media=FakeFFmpeg(has_audio=False), provider=_provider(handler)),
        )
        arguments = ["analyze", str(video), "--runs-root", str(runs_root)]
    else:
        monkeypatch.setattr(
            "vidsnap.cli.InterviewRecipeRunner",
            lambda: InterviewRecipeRunner(
                media=FakeInterviewMedia(),
                recognizer=FakeInterviewTranscriber(),
                provider=_provider(handler),
            ),
        )
        arguments = [
            "recipe",
            "interview",
            str(video),
            "--output-dir",
            str(tmp_path / "out"),
            "--runs-root",
            str(runs_root),
        ]
    result = CliRunner().invoke(app, arguments)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    run_path = Path(json.loads(result.stdout)["run_path"])
    return result.output, run_path, runs_root


@pytest.mark.parametrize("command", ["analyze", "recipe interview"])
@pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
def test_failing_provider_run_leaks_nothing_anywhere(
    scenario: str, command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, run_path, runs_root = _run_command(command, _SCENARIOS[scenario], tmp_path, monkeypatch)
    html_path = tmp_path / "trace.html"
    export = CliRunner().invoke(app, ["trace", "export", str(run_path), "--output", str(html_path)])
    assert export.exit_code == 0, export.output

    surfaces = {
        "command output": output + export.output,
        "events.jsonl": (run_path / "events.jsonl").read_text(encoding="utf-8"),
        "manifest.json": (run_path / "manifest.json").read_text(encoding="utf-8"),
        "index.jsonl": (runs_root / "index.jsonl").read_text(encoding="utf-8"),
        "trace.html": html_path.read_text(encoding="utf-8"),
    }
    for surface, text in surfaces.items():
        for needle in _NEEDLES:
            assert needle not in text, f"{surface} leaked {needle!r} in {scenario}"

    # The mocked transport really was exercised: the failure is recorded by category only.
    (record,) = [json.loads(line) for line in surfaces["index.jsonl"].splitlines()]
    assert record["terminal_state"] == "FAILED"
    assert (record["failure_category"], record["http_status"]) == _EXPECTED[scenario]
