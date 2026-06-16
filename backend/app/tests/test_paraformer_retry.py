import asyncio
from types import SimpleNamespace

import requests

from app.services import paraformer_service as paraformer_module
from app.services.paraformer_service import ParaformerSpeechService


def _service() -> ParaformerSpeechService:
    service = ParaformerSpeechService()
    service.api_key = "test-key"
    service.available = True
    return service


def _patch_fast_retry(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(paraformer_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(paraformer_module.settings, "PARAFORMER_TRANSCRIPTION_SUBMIT_RETRIES", 3)
    monkeypatch.setattr(paraformer_module.settings, "PARAFORMER_TRANSCRIPTION_FETCH_RETRIES", 3)
    monkeypatch.setattr(paraformer_module.settings, "PARAFORMER_TRANSCRIPTION_RETRY_BASE_SECONDS", 0)
    monkeypatch.setattr(paraformer_module.settings, "PARAFORMER_MAX_WAIT_SECONDS", 30)
    monkeypatch.setattr(paraformer_module.settings, "PARAFORMER_POLL_INTERVAL_SECONDS", 1)


def test_submit_retries_transient_ssl_error(monkeypatch):
    _patch_fast_retry(monkeypatch)
    service = _service()
    calls = {"submit": 0}

    def fake_async_call(**_kwargs):
        calls["submit"] += 1
        if calls["submit"] == 1:
            raise requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")
        return SimpleNamespace(status_code=200, output=SimpleNamespace(task_id="task-ok"))

    def fake_fetch(task):
        assert task == "task-ok"
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(task_status="SUCCEEDED", results=[]),
        )

    monkeypatch.setattr(
        paraformer_module.Transcription,
        "async_call",
        staticmethod(fake_async_call),
    )
    monkeypatch.setattr(paraformer_module.Transcription, "fetch", staticmethod(fake_fetch))

    output = asyncio.run(service.transcribe_audio_with_timestamps("https://oss.example/audio.wav"))

    assert output.task_status == "SUCCEEDED"
    assert calls["submit"] == 2


def test_fetch_retries_transient_connection_error(monkeypatch):
    _patch_fast_retry(monkeypatch)
    service = _service()
    calls = {"fetch": 0}

    def fake_async_call(**_kwargs):
        return SimpleNamespace(status_code=200, output=SimpleNamespace(task_id="task-ok"))

    def fake_fetch(task):
        assert task == "task-ok"
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            raise requests.exceptions.ConnectionError("connection reset")
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(task_status="SUCCEEDED", results=[]),
        )

    monkeypatch.setattr(
        paraformer_module.Transcription,
        "async_call",
        staticmethod(fake_async_call),
    )
    monkeypatch.setattr(paraformer_module.Transcription, "fetch", staticmethod(fake_fetch))

    output = asyncio.run(service.transcribe_audio_with_timestamps("https://oss.example/audio.wav"))

    assert output.task_status == "SUCCEEDED"
    assert calls["fetch"] == 2


def test_submit_does_not_retry_business_400(monkeypatch):
    _patch_fast_retry(monkeypatch)
    service = _service()
    calls = {"submit": 0}

    def fake_async_call(**_kwargs):
        calls["submit"] += 1
        return SimpleNamespace(status_code=400, message="Access denied", output=None)

    monkeypatch.setattr(
        paraformer_module.Transcription,
        "async_call",
        staticmethod(fake_async_call),
    )

    output = asyncio.run(service.transcribe_audio_with_timestamps("https://oss.example/audio.wav"))

    assert output is None
    assert calls["submit"] == 1
