"""Cost is computed only from a user-supplied price table; unknown is never zero."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from vidsnap.trace.pricing import load_price_table, price_run


def _write_table(path: Path, models: dict[str, object], **extra: object) -> Path:
    table = {"schema_version": "vidsnap.price-table/v1", "currency": "CNY", "models": models}
    table.update(extra)
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def test_price_table_is_validated_and_fingerprinted(tmp_path: Path) -> None:
    path = _write_table(
        tmp_path / "prices.json",
        {"example-model": {"input_per_million_tokens": 2.0, "output_per_million_tokens": 8.0}},
    )

    loaded = load_price_table(path)

    assert loaded.table.currency == "CNY"
    assert loaded.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": "vidsnap.price-table/v0"},
        {"currency": ""},
        {"models": {}},
        {"models": {"m": {"input_per_million_tokens": -1, "output_per_million_tokens": 1}}},
        {"models": {"m": {"input_per_million_tokens": 1}}},
        {"models": {"m": {"input_per_million_tokens": 1, "output_per_million_tokens": 1, "x": 1}}},
        {"unexpected": True},
    ],
)
def test_invalid_price_tables_are_refused(tmp_path: Path, mutation: dict[str, object]) -> None:
    table: dict[str, object] = {
        "schema_version": "vidsnap.price-table/v1",
        "currency": "CNY",
        "models": {"m": {"input_per_million_tokens": 1, "output_per_million_tokens": 1}},
    }
    table.update(mutation)
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(table), encoding="utf-8")

    with pytest.raises(ValueError):
        load_price_table(path)


def test_unreadable_price_table_is_refused(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_price_table(tmp_path / "broken.json")
    with pytest.raises(ValueError):
        load_price_table(tmp_path / "missing.json")


def _loaded(tmp_path: Path) -> object:
    return load_price_table(
        _write_table(
            tmp_path / "prices.json",
            {"example-model": {"input_per_million_tokens": 2.0, "output_per_million_tokens": 8.0}},
        )
    )


def test_complete_reported_usage_is_priced_exactly(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)

    cost = price_run(
        model="example-model",
        model_requests=2,
        input_tokens=1_000_000,
        output_tokens=250_000,
        tokens_reported=True,
        speech_recognition=False,
        price_table=loaded,
    )

    assert cost == {
        "amount": 4.0,
        "currency": "CNY",
        "model": "example-model",
        "complete": True,
        "note": None,
        "price_table_sha256": loaded.sha256,
    }


def test_no_price_table_means_no_cost_record() -> None:
    assert (
        price_run(
            model="example-model",
            model_requests=1,
            input_tokens=10,
            output_tokens=10,
            tokens_reported=True,
            speech_recognition=False,
            price_table=None,
        )
        is None
    )


@pytest.mark.parametrize(
    ("model", "tokens_reported", "note"),
    [
        (None, True, "model_unknown"),
        ("other-model", True, "model_not_in_price_table"),
        ("example-model", False, "usage_not_reported"),
    ],
)
def test_unpriceable_runs_record_a_null_amount_and_why(
    tmp_path: Path, model: str | None, tokens_reported: bool, note: str
) -> None:
    loaded = _loaded(tmp_path)

    cost = price_run(
        model=model,
        model_requests=1,
        input_tokens=100,
        output_tokens=100,
        tokens_reported=tokens_reported,
        speech_recognition=False,
        price_table=loaded,
    )

    assert cost is not None
    assert cost["amount"] is None
    assert cost["complete"] is False
    assert cost["note"] == note
    assert cost["currency"] == "CNY"


def test_a_run_without_model_requests_is_never_priced_as_zero(tmp_path: Path) -> None:
    cost = price_run(
        model="example-model",
        model_requests=0,
        input_tokens=0,
        output_tokens=0,
        tokens_reported=True,
        speech_recognition=False,
        price_table=_loaded(tmp_path),
    )

    assert cost is not None
    assert cost["amount"] is None
    assert cost["complete"] is False
    assert cost["note"] == "no_model_requests"


def test_speech_recognition_makes_the_priced_amount_incomplete(tmp_path: Path) -> None:
    cost = price_run(
        model="example-model",
        model_requests=1,
        input_tokens=1_000_000,
        output_tokens=0,
        tokens_reported=True,
        speech_recognition=True,
        price_table=_loaded(tmp_path),
    )

    assert cost is not None
    assert cost["amount"] == 2.0
    assert cost["complete"] is False
    assert cost["note"] == "speech_recognition_not_priced"
