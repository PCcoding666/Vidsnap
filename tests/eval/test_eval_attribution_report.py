"""Loss attribution, trace-based cost, safe rendering and the report's stated conclusions."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

from tests.eval.helpers import make_item, price_table
from vidsnap.contracts import default_loop_spec
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.eval.attribution import loss_stage
from vidsnap.eval.costs import estimate_cost, frame_tokens, load_eval_prices, run_cost
from vidsnap.eval.render import (
    captions_srt,
    html_valid,
    png_is_not_blank,
    storyboard_html,
)
from vidsnap.eval.report import build_report, findings, group_rows
from vidsnap.eval.review import markdown_to_html
from vidsnap.eval.suite import KeyPoint
from vidsnap.eval.tasks import StoryboardOutput
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.providers.base import ProviderIdentity


def point(modality: str, window: tuple[float, float] | None = (10, 20)) -> KeyPoint:
    return KeyPoint(id="kp", text="t", match=[["判别式"]], modality=modality, window=window)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("modality", "transcript", "frames", "window", "expected"),
    [
        ("speech", "这里讲了判别式", [], (10, 20), "lost_at_synthesis"),
        ("speech", "没有提到", [], (10, 20), "lost_at_asr"),
        ("speech", None, [], (10, 20), "lost_at_asr"),
        ("visual", None, [15.0], (10, 20), "lost_at_synthesis"),
        ("visual", None, [60.0], (10, 20), "lost_at_sampling"),
        ("visual", None, [15.0], None, "unattributed"),
        ("both", "没有提到", [60.0], (10, 20), "lost_at_perception"),
        ("both", "没有提到", [12.0], (10, 20), "lost_at_synthesis"),
        ("both", "判别式", [60.0], (10, 20), "lost_at_synthesis"),
        ("both", "没有提到", [], None, "lost_at_asr"),
    ],
)
def test_loss_stage_rules(
    modality: str,
    transcript: str | None,
    frames: list[float],
    window: tuple[float, float] | None,
    expected: str,
) -> None:
    assert (
        loss_stage(point(modality, window), transcript_text=transcript, frame_times=frames)
        == expected
    )


def native_bundle(
    tmp_path: Path, model: str, usage: ProviderUsage, details: dict[str, Any]
) -> Path:
    identity = ProviderIdentity(id="qwen", model=model, base_url="https://example.invalid/v1")
    bundle = RunBundle.create(
        tmp_path / "bundle",
        loop_spec=default_loop_spec(),
        provider_url=identity.base_url,
        provider_identity=identity,
    )
    trace = TraceRecorder(bundle)
    run = trace.start(
        "run",
        phase="run",
        payload={"provider": {"id": "qwen", "model": model}, "speech_recognizer": None},
    )
    span = trace.start("model.request", phase="native_video")
    trace.finish(span, status="completed", payload={"usage_details": details}, usage=usage)
    trace.finish(run, status="completed")
    bundle.finalize("SUCCEEDED")
    return bundle.path


def test_native_cost_prices_audio_tokens_separately(tmp_path: Path) -> None:
    prices = load_eval_prices(price_table(tmp_path / "prices.json"))
    usage = ProviderUsage(model_calls=1, input_tokens=10_000, output_tokens=1_000, reported=True)
    bundle = native_bundle(tmp_path, "qwen3.5-omni-plus", usage, {"input_audio": 2_000})
    cost = run_cost(bundle, prices)
    assert cost is not None
    expected = (8_000 * 7 + 2_000 * 53 + 1_000 * 40) / 1_000_000
    assert cost["amount"] == pytest.approx(expected)
    assert cost["speech_amount"] == 0.0


def test_unreported_usage_is_never_priced_as_zero(tmp_path: Path) -> None:
    prices = load_eval_prices(price_table(tmp_path / "prices.json"))
    usage = ProviderUsage(model_calls=1, reported=False)
    bundle = native_bundle(tmp_path, "qwen3.8-omni-flash", usage, {})
    cost = run_cost(bundle, prices)
    assert cost is not None and cost["amount"] is None
    assert "usage_not_reported" in cost["notes"]
    assert run_cost(bundle, None) is None


def test_estimates_use_measured_sampling(tmp_path: Path) -> None:
    prices = load_eval_prices(price_table(tmp_path / "prices.json"))
    assert frame_tokens(1280, 720) == 46 * 26
    guess = estimate_cost("harness", "qwen3.8-max", 600, True, prices)
    measured = estimate_cost(
        "harness", "qwen3.8-max", 600, True, prices, measured_frames=96, tokens_per_frame=120
    )
    assert guess is not None and measured is not None and measured != guess
    assert estimate_cost("harness", "unknown-model", 600, True, prices) is None


def test_storyboard_html_escapes_model_text() -> None:
    storyboard = StoryboardOutput.model_validate(
        {
            "title": "</title><script>alert(1)</script>",
            "scenes": [
                {
                    "title": "</script><img src=x onerror=alert(1)>",
                    "start_seconds": 0,
                    "end_seconds": 10,
                    "captions": [{"start_seconds": 1, "end_seconds": 4, "text": "第一句"}],
                }
            ],
        }
    )
    html = storyboard_html(storyboard)
    assert "<script>alert(1)" not in html
    assert "</script><img" not in html
    assert html_valid(html)
    assert "http" not in html.lower().replace("http-equiv", "")
    srt = captions_srt(storyboard)
    assert "00:00:01,000 --> 00:00:04,000\n第一句" in srt


def _png(width: int, height: int, pixel: Any) -> bytes:
    rows = b"".join(
        b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height)
    )

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def test_blank_frames_are_detected() -> None:
    assert not png_is_not_blank(_png(40, 30, lambda x, y: (17, 20, 24)))
    assert png_is_not_blank(_png(40, 30, lambda x, y: (250, 250, 250) if x < 10 else (17, 20, 24)))
    assert not png_is_not_blank(b"not a png")


def test_review_markdown_is_escaped(tmp_path: Path) -> None:
    html = markdown_to_html(
        "# 标题<script>\n\n- **粗体** <b>x</b>\n\n![a](../../etc/passwd)", tmp_path
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<strong>粗体</strong>" in html and "&lt;b&gt;" in html
    assert "passwd" not in html.split("图片未嵌入")[0] or "data:image" not in html


def result_document(
    system: str, kind: str, items: dict[str, dict[str, Any]], *, model: str = "qwen3.8-max"
) -> dict[str, Any]:
    base = system.split("+oracle")[0] if kind == "harness" else system
    return {
        "schema_version": "vidsnap.eval-result/v1",
        "suite_id": "t1",
        "task": "t1",
        "system": system,
        "system_kind": kind,
        "model": model,
        "base_system": base,
        "currency": "CNY",
        "started_at": "2026-10-10T00:00:00Z",
        "items": [{"item_id": item_id, **record} for item_id, record in items.items()],
    }


def record(
    primary: float, coverage: float, *, asr_losses: int = 0, cost: float = 0.1
) -> dict[str, Any]:
    return {
        "terminal_state": "SUCCEEDED",
        "duration_ms": 1000,
        "cost": {"amount": cost},
        "machine": {
            "success": True,
            "primary": primary,
            "key_point_coverage": coverage,
            "moment_recall": 0.5,
        },
        "stages": {
            "asr_cer": 0.3,
            "frame_moment_recall": 1.0,
            "losses": {"lost_at_asr": asr_losses, "lost_at_synthesis": 1},
            "timings_ms": {"tool:transcribe_audio": 500, "model:synthesize_result": 500},
        },
    }


def test_findings_name_the_limiting_component_only_with_enough_items() -> None:
    items = [f"t1-{index}" for index in range(3)]
    harness = result_document(
        "harness+qwen3.8-max", "harness", {i: record(0.4, 0.4, asr_losses=3) for i in items}
    )
    oracle = result_document(
        "harness+qwen3.8-max+oracle-asr", "harness", {i: record(0.7, 0.8) for i in items}
    )
    native = result_document(
        "native:qwen3.8-omni-flash",
        "native",
        {i: record(0.6, 0.6) for i in items},
        model="qwen3.8-omni-flash",
    )
    rows = sorted(group_rows([harness, oracle, native]).values(), key=lambda row: row.system)
    statements = findings(rows, [])
    assert any("optimise ASR" in statement for statement in statements)
    assert any("native:qwen3.8-omni-flash beats harness+qwen3.8-max" in s for s in statements)
    report = build_report([harness, oracle, native])
    assert "| t1 | harness+qwen3.8-max | harness+qwen3.8-max+oracle-asr | 3 | 0.300 |" in report

    few = result_document(
        "harness+qwen3.8-max", "harness", {"only": record(0.4, 0.4, asr_losses=3)}
    )
    assert any("insufficient evidence" in s for s in findings(list(group_rows([few]).values()), []))


def test_results_must_be_eval_result_files(tmp_path: Path) -> None:
    from vidsnap.eval.report import load_results

    bogus = tmp_path / "x.json"
    bogus.write_text(json.dumps({"schema_version": "other"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_results([bogus])
    assert make_item().item_id == "x-01"
