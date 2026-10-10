"""Cost from traces with a user-supplied ``vidsnap.eval-price-table/v1``; never guessed.

Model cost is the run's model-request tokens times the table's prices, with
audio input priced separately when the model has an audio price and the trace
recorded the audio token count. ASR cost is the transcribed audio seconds (the
``transcribe_audio`` windows in the trace) times the ASR price. Anything that
cannot be measured makes the amount ``None``; unknown is never zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, JsonValue, ValidationError

from vidsnap.contracts.models import StrictModel
from vidsnap.eval.attribution import read_events
from vidsnap.loop.events import RunEvent
from vidsnap.trace.pricing import LoadedPriceTable, ModelPrice, PriceTable

EVAL_PRICE_SCHEMA = "vidsnap.eval-price-table/v1"
FREE_PROVIDERS = frozenset({"mock", "oracle"})


class EvalModelPrice(StrictModel):
    """Prices per million tokens (or per second of audio for ASR models)."""

    input_per_million_tokens: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_per_million_tokens: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    audio_input_per_million_tokens: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    speech_per_second: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class EvalPriceTable(StrictModel):
    schema_version: Literal["vidsnap.eval-price-table/v1"]
    currency: str = Field(min_length=1, max_length=16)
    source: str = Field(min_length=1, max_length=1000)
    checked_on: str = Field(min_length=1, max_length=32)
    models: dict[str, EvalModelPrice] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LoadedEvalPrices:
    table: EvalPriceTable
    sha256: str

    def run_index_table(self) -> LoadedPriceTable | None:
        """The token prices as a ``vidsnap.price-table/v1`` for the run index."""
        models = {
            name: ModelPrice(
                input_per_million_tokens=price.input_per_million_tokens,
                output_per_million_tokens=price.output_per_million_tokens,
            )
            for name, price in self.table.models.items()
            if price.input_per_million_tokens is not None
            and price.output_per_million_tokens is not None
        }
        if not models:
            return None
        table = PriceTable(
            schema_version="vidsnap.price-table/v1", currency=self.table.currency, models=models
        )
        return LoadedPriceTable(table=table, sha256=self.sha256)


def load_eval_prices(path: Path) -> LoadedEvalPrices:
    try:
        raw = path.read_bytes()
        table = EvalPriceTable.model_validate(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"eval price table is missing or invalid: {path}") from error
    return LoadedEvalPrices(table=table, sha256=hashlib.sha256(raw).hexdigest())


def _header(events: list[RunEvent]) -> dict[str, Any]:
    for event in events:
        if event.event_type == "run.started":
            return dict(event.payload)
    return {}


def _identity(header: dict[str, Any], key: str) -> tuple[str | None, str | None]:
    value = header.get(key)
    if not isinstance(value, dict):
        return None, None
    provider = value.get("id")
    model = value.get("model")
    return (
        provider if isinstance(provider, str) else None,
        model if isinstance(model, str) else None,
    )


def _speech_seconds(events: list[RunEvent], duration: float | None) -> float | None:
    """Seconds of audio sent to ASR, from the logged ``transcribe_audio`` windows."""
    seconds = 0.0
    for event in events:
        if (
            event.event_type != "tool.call.started"
            or event.payload.get("name") != "transcribe_audio"
        ):
            continue
        arguments = event.payload.get("arguments")
        windows = arguments.get("windows") if isinstance(arguments, dict) else None
        if isinstance(windows, list) and windows:
            for window in windows:
                if not isinstance(window, dict):
                    return None
                start, end = window.get("start_seconds"), window.get("end_seconds")
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                    return None
                seconds += float(end) - float(start)
        elif duration is None:
            return None
        else:
            seconds += duration
    return seconds


def _probe_duration(events: list[RunEvent]) -> float | None:
    for event in events:
        if event.event_type == "probe.completed":
            value = event.payload.get("duration_seconds")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _asr_ran(events: list[RunEvent]) -> bool:
    return any(
        (event.event_type or "") in ("tool.call.completed", "tool.call.failed")
        and event.payload.get("name") == "transcribe_audio"
        for event in events
    )


def _audio_tokens(event: RunEvent) -> int | None:
    details = event.payload.get("usage_details")
    if isinstance(details, dict):
        value = details.get("input_audio")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def run_cost(bundle: Path, prices: LoadedEvalPrices | None) -> dict[str, JsonValue] | None:
    """Price one finished run from its trace; ``None`` without a price table."""
    if prices is None:
        return None
    events = read_events(bundle)
    header = _header(events)
    provider, model = _identity(header, "provider")
    speech_provider, speech_model = _identity(header, "speech_recognizer")
    notes: list[str] = []
    model_amount: float | None = 0.0
    requests = [
        event
        for event in events
        if event.event_type in ("model.request.completed", "model.request.failed")
    ]
    if provider in FREE_PROVIDERS:
        model_amount = 0.0
    elif requests:
        price = prices.table.models.get(model or "")
        if (
            price is None
            or price.input_per_million_tokens is None
            or price.output_per_million_tokens is None
        ):
            model_amount = None
            notes.append("model_not_in_price_table")
        else:
            total = 0.0
            for event in requests:
                if event.usage is None or not event.usage.provider_reported:
                    model_amount = None
                    notes.append("usage_not_reported")
                    break
                audio = _audio_tokens(event)
                input_tokens = event.usage.input_tokens
                if audio and price.audio_input_per_million_tokens is not None:
                    total += audio * price.audio_input_per_million_tokens
                    input_tokens -= audio
                elif audio and price.audio_input_per_million_tokens is None:
                    notes.append("audio_priced_as_input")
                total += input_tokens * price.input_per_million_tokens
                total += event.usage.output_tokens * price.output_per_million_tokens
            if model_amount is not None:
                model_amount = total / 1_000_000
    asr_amount: float | None = 0.0
    seconds: float | None = 0.0
    if _asr_ran(events) and speech_provider not in FREE_PROVIDERS:
        seconds = _speech_seconds(events, _probe_duration(events))
        speech_price = prices.table.models.get(speech_model or "")
        if speech_price is None or speech_price.speech_per_second is None:
            asr_amount = None
            notes.append("speech_model_not_in_price_table")
        elif seconds is None:
            asr_amount = None
            notes.append("speech_seconds_unknown")
        else:
            asr_amount = seconds * speech_price.speech_per_second
    amount = (
        round(model_amount + asr_amount, 6)
        if model_amount is not None and asr_amount is not None
        else None
    )
    note_values: list[JsonValue] = [*sorted(set(notes))]
    return {
        "amount": amount,
        "currency": prices.table.currency,
        "model": model,
        "model_amount": round(model_amount, 6) if model_amount is not None else None,
        "speech_model": speech_model,
        "speech_seconds": round(seconds, 3) if seconds is not None else None,
        "speech_amount": round(asr_amount, 6) if asr_amount is not None else None,
        "notes": note_values,
        "price_table_sha256": prices.sha256,
    }


# Assumptions for planning estimates only; see docs/eval.md "Cost".
NATIVE_TOKENS_PER_SECOND = 600
NATIVE_AUDIO_TOKENS_PER_SECOND = 25
NATIVE_OUTPUT_TOKENS = 8000
HARNESS_TOKENS_PER_FRAME = 1200
HARNESS_TRANSCRIPT_TOKENS_PER_SECOND = 5
HARNESS_PROMPT_TOKENS = 2000
HARNESS_OUTPUT_TOKENS = 6000
HARNESS_FRAMES_PER_MINUTE = 4
HARNESS_MAX_FRAMES = 96


def frame_tokens(width: int, height: int) -> int:
    """Visual tokens for one frame at Qwen-VL's 28-pixel granularity."""
    return max(4, -(-width // 28) * -(-height // 28))


def estimate_cost(
    system_kind: str,
    model: str,
    duration_seconds: float,
    has_audio: bool,
    prices: LoadedEvalPrices,
    *,
    speech_model: str = "qwen3-asr-flash",
    measured_frames: int | None = None,
    tokens_per_frame: int | None = None,
) -> float | None:
    """A planning estimate for one item; ``None`` when a needed price is missing.

    For the harness, ``measured_frames`` and ``tokens_per_frame`` come from an
    offline sampling run (sampling never calls a model, so a mock run on the real
    media measures it exactly); otherwise fixed assumptions are used.
    """
    price = prices.table.models.get(model)
    if (
        price is None
        or price.input_per_million_tokens is None
        or price.output_per_million_tokens is None
    ):
        return None
    if system_kind == "native":
        tokens = duration_seconds * NATIVE_TOKENS_PER_SECOND
        audio = duration_seconds * NATIVE_AUDIO_TOKENS_PER_SECOND if has_audio else 0.0
        audio_price = (
            price.audio_input_per_million_tokens
            if price.audio_input_per_million_tokens is not None
            else price.input_per_million_tokens
        )
        return (
            (tokens - audio) * price.input_per_million_tokens
            + audio * audio_price
            + NATIVE_OUTPUT_TOKENS * price.output_per_million_tokens
        ) / 1_000_000
    frames = (
        float(measured_frames)
        if measured_frames is not None
        else min(HARNESS_MAX_FRAMES, 8 + duration_seconds / 60 * HARNESS_FRAMES_PER_MINUTE)
    )
    input_tokens = (
        frames * (tokens_per_frame or HARNESS_TOKENS_PER_FRAME)
        + duration_seconds * HARNESS_TRANSCRIPT_TOKENS_PER_SECOND
        + HARNESS_PROMPT_TOKENS
    )
    amount = (
        input_tokens * price.input_per_million_tokens
        + HARNESS_OUTPUT_TOKENS * price.output_per_million_tokens
    ) / 1_000_000
    if has_audio:
        speech = prices.table.models.get(speech_model)
        if speech is None or speech.speech_per_second is None:
            return None
        amount += duration_seconds * speech.speech_per_second
    return amount
