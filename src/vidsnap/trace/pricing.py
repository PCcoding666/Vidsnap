"""Cost from a user-supplied price table only; VidSnap ships no prices.

Without a price table there is no cost record. With one, a run's model
requests are priced only when the run made at least one, its model is known
and listed in the table, and every request reported its token usage;
otherwise the amount is ``None`` with a note saying why. ``complete`` is true
only when the amount covers every provider call the run made: speech
recognition is not priced, so a run that used it is never complete. Unknown is
never zero.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, ValidationError

from vidsnap.contracts.models import StrictModel

PRICE_TABLE_SCHEMA = "vidsnap.price-table/v1"


class ModelPrice(StrictModel):
    """Prices for one model, per million tokens, in the table's currency."""

    input_per_million_tokens: float = Field(ge=0, allow_inf_nan=False)
    output_per_million_tokens: float = Field(ge=0, allow_inf_nan=False)


class PriceTable(StrictModel):
    """A user-maintained ``vidsnap.price-table/v1`` document."""

    schema_version: Literal["vidsnap.price-table/v1"]
    currency: str = Field(min_length=1, max_length=16)
    models: dict[str, ModelPrice] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LoadedPriceTable:
    """A validated price table plus the SHA-256 of the exact file it came from."""

    table: PriceTable
    sha256: str


def load_price_table(path: Path) -> LoadedPriceTable:
    """Read and strictly validate one price table; raise ``ValueError`` otherwise."""
    try:
        raw = path.read_bytes()
        table = PriceTable.model_validate(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"price table is missing or invalid: {path}") from error
    return LoadedPriceTable(table=table, sha256=hashlib.sha256(raw).hexdigest())


def price_run(
    *,
    model: str | None,
    model_requests: int,
    input_tokens: int,
    output_tokens: int,
    tokens_reported: bool,
    speech_recognition: bool,
    price_table: LoadedPriceTable | None,
) -> dict[str, JsonValue] | None:
    """Price one run's model-request tokens, or explain why it cannot be priced."""
    if price_table is None:
        return None
    note: str | None = None
    amount: float | None = None
    price = price_table.table.models.get(model) if model is not None else None
    if model_requests == 0:
        note = "no_model_requests"
    elif model is None:
        note = "model_unknown"
    elif price is None:
        note = "model_not_in_price_table"
    elif not tokens_reported:
        note = "usage_not_reported"
    else:
        amount = round(
            (
                input_tokens * price.input_per_million_tokens
                + output_tokens * price.output_per_million_tokens
            )
            / 1_000_000,
            10,
        )
        if speech_recognition:
            note = "speech_recognition_not_priced"
    return {
        "amount": amount,
        "currency": price_table.table.currency,
        "model": model,
        "complete": amount is not None and not speech_recognition,
        "note": note,
        "price_table_sha256": price_table.sha256,
    }
