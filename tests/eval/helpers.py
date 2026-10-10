"""Shared builders for the offline evaluation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vidsnap.eval.suite import EvalItem, LoadedSuite, load_suite

REPO = Path(__file__).resolve().parents[2]
SUITES_DIR = REPO / "benchmarks" / "eval" / "suites"


def committed_suite(task: str) -> LoadedSuite:
    return load_suite(task, SUITES_DIR)


def item_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "item_id": "x-01",
        "status": "ready",
        "source": {
            "kind": "public",
            "path": "public/x.mp4",
            "sha256": "0" * 64,
            "duration_seconds": 60.0,
            "licence": "test",
            "language": "zh",
            "has_audio": True,
        },
        "inputs": {"goal": "测试目标"},
        "reference": {
            "transcript": {
                "language": "zh",
                "segments": [{"start_seconds": 0, "end_seconds": 60, "text": "判别式是b平方减4ac"}],
            },
            "key_points": [
                {
                    "id": "kp-a",
                    "text": "判别式",
                    "match": [["判别式"]],
                    "modality": "speech",
                    "window": [0, 30],
                },
                {
                    "id": "kp-b",
                    "text": "屏幕上的数字 3.35",
                    "match": [["3.35"]],
                    "modality": "visual",
                    "window": [30, 40],
                },
            ],
            "key_moments": [
                {"id": "km-a", "at_seconds": 10, "tolerance_seconds": 3, "description": "a"}
            ],
            "entities": ["Llama 3 8B"],
            "forbidden": [{"id": "fb-a", "text": "错误说法", "match": [["计算受限的decode"]]}],
        },
    }
    payload.update(overrides)
    return payload


def make_item(**overrides: Any) -> EvalItem:
    return EvalItem.model_validate(item_payload(**overrides))


def write_suite(path: Path, task: str, items: list[dict[str, Any]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "vidsnap.eval-suite/v1",
                "suite_id": task,
                "task": task,
                "title": "test",
                "description": "test",
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def price_table(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "vidsnap.eval-price-table/v1",
                "currency": "CNY",
                "source": "test fixture",
                "checked_on": "2026-10-10",
                "models": {
                    "qwen3.8-max": {
                        "input_per_million_tokens": 12,
                        "output_per_million_tokens": 36,
                    },
                    "qwen3.8-omni-flash": {
                        "input_per_million_tokens": 0.8,
                        "output_per_million_tokens": 2.7,
                    },
                    "qwen3.5-omni-plus": {
                        "input_per_million_tokens": 7,
                        "audio_input_per_million_tokens": 53,
                        "output_per_million_tokens": 40,
                    },
                    "qwen-audio-3.1-asr-flash": {"speech_per_second": 0.00022},
                },
            }
        ),
        encoding="utf-8",
    )
    return path
