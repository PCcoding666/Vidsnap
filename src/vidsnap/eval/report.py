"""Aggregate eval results (and human scores) into one Markdown comparison report.

Thresholds for stated conclusions live here, in one reviewed place; they are the
ones documented in ``docs/eval.md``. A conclusion is stated only when enough
scored items support it; otherwise the report says the evidence is insufficient.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from pydantic import Field, ValidationError

from vidsnap.contracts.models import StrictModel
from vidsnap.eval.attribution import LOSS_STAGES
from vidsnap.eval.costs import LoadedEvalPrices, estimate_cost, frame_tokens
from vidsnap.eval.suite import LoadedSuite
from vidsnap.eval.systems import list_systems, parse_system

HUMAN_SCHEMA = "vidsnap.eval-human/v1"
MIN_ITEMS = 3
LOSS_SHARE = 0.30
ASR_ERROR_LIMIT = 0.15
FRAME_RECALL_LIMIT = 0.70
MIN_GAIN = 0.10
MAX_COST_RATIO = 1.5


class HumanScore(StrictModel):
    suite_id: str
    item_id: str
    system: str
    dimensions: dict[str, int] = Field(default_factory=dict)
    preferred: bool | None = None
    edit_minutes: float | None = Field(default=None, ge=0)
    note: str | None = None


class HumanScores(StrictModel):
    schema_version: str = HUMAN_SCHEMA
    reviewer: str | None = None
    created_at: str | None = None
    scores: list[HumanScore] = Field(default_factory=list)


@dataclass(slots=True)
class SystemRows:
    """All item records of one system on one suite, merged across result files."""

    suite_id: str
    task: str
    system: str
    kind: str
    model: str
    base_system: str
    currency: str | None = None
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    skipped: Counter[str] = field(default_factory=Counter)


def load_results(paths: Iterable[Path]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != "vidsnap.eval-result/v1":
            raise ValueError(f"not an eval result file: {path}")
        documents.append(data)
    return documents


def load_human(paths: Iterable[Path]) -> list[HumanScore]:
    scores: list[HumanScore] = []
    for path in paths:
        try:
            scores.extend(HumanScores.model_validate_json(path.read_text(encoding="utf-8")).scores)
        except (OSError, ValidationError) as error:
            raise ValueError(f"not a human score file: {path}") from error
    return scores


def group_rows(documents: Sequence[dict[str, Any]]) -> dict[tuple[str, str], SystemRows]:
    """Latest record per (suite, system, item); later files override earlier ones."""
    rows: dict[tuple[str, str], SystemRows] = {}
    for document in sorted(documents, key=lambda doc: str(doc.get("started_at"))):
        key = (str(document["suite_id"]), str(document["system"]))
        row = rows.setdefault(
            key,
            SystemRows(
                suite_id=key[0],
                task=str(document.get("task")),
                system=key[1],
                kind=str(document.get("system_kind")),
                model=str(document.get("model")),
                base_system=str(document.get("base_system") or key[1]),
            ),
        )
        row.currency = document.get("currency") or row.currency
        for record in document.get("items") or []:
            if not isinstance(record, dict):
                continue
            if "skipped" in record:
                row.skipped[str(record["skipped"]).split(":")[0]] += 1
                continue
            row.items[str(record["item_id"])] = record
    return rows


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _mean(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(mean(present), 3) if present else None


def _fmt(value: float | None, digits: int = 2) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _machine(record: dict[str, Any], name: str) -> float | None:
    machine = record.get("machine")
    return _num(machine.get(name)) if isinstance(machine, dict) else None


def _stage(record: dict[str, Any], name: str) -> Any:
    stages = record.get("stages")
    return stages.get(name) if isinstance(stages, dict) else None


def _cost(record: dict[str, Any]) -> float | None:
    cost = record.get("cost")
    return _num(cost.get("amount")) if isinstance(cost, dict) else None


def _succeeded(record: dict[str, Any]) -> bool:
    machine = record.get("machine")
    return isinstance(machine, dict) and machine.get("success") is True


def _human_for(scores: Sequence[HumanScore], row: SystemRows) -> list[HumanScore]:
    return [s for s in scores if s.suite_id == row.suite_id and s.system == row.system]


def _human_mean(scores: Sequence[HumanScore]) -> float | None:
    values = [mean(score.dimensions.values()) for score in scores if score.dimensions]
    return round(mean(values), 2) if values else None


def _preference(scores: Sequence[HumanScore]) -> float | None:
    votes = [score.preferred for score in scores if score.preferred is not None]
    return round(sum(1 for vote in votes if vote) / len(votes), 2) if votes else None


def overview_table(rows: Sequence[SystemRows], human: Sequence[HumanScore]) -> list[str]:
    lines = [
        "| System | Run | OK | Failures | Primary | Key points | Moments | Structure | "
        "Entities | Halluc. | Human (1-5) | Preferred | Cost total | Cost/item | "
        "Latency p50 s | Latency max s | Upload MB/item |",
        "|" + "---|" * 17,
    ]
    for row in rows:
        records = list(row.items.values())
        failures = Counter(
            str(record.get("failure_category") or record.get("terminal_state"))
            for record in records
            if not _succeeded(record)
        )
        costs = [_cost(record) for record in records]
        known_costs = [cost for cost in costs if cost is not None]
        latencies = [
            value / 1000 for record in records if (value := _num(record.get("duration_ms")))
        ]
        humans = _human_for(human, row)
        total_cost = (
            round(sum(known_costs), 4) if known_costs and len(known_costs) == len(costs) else None
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    row.system,
                    str(len(records)),
                    str(sum(1 for record in records if _succeeded(record))),
                    ", ".join(f"{name}×{count}" for name, count in failures.items()) or "–",
                    _fmt(_mean(_machine(r, "primary") for r in records)),
                    _fmt(_mean(_machine(r, "key_point_coverage") for r in records)),
                    _fmt(_mean(_machine(r, "moment_recall") for r in records)),
                    _fmt(_mean(_machine(r, "structure") for r in records)),
                    _fmt(_mean(_machine(r, "entity_recall") for r in records)),
                    _fmt(_mean(_machine(r, "hallucinations") for r in records), 1),
                    _fmt(_human_mean(humans)),
                    _fmt(_preference(humans)),
                    _fmt(total_cost, 4) + (f" {row.currency}" if total_cost is not None else ""),
                    _fmt(
                        round(total_cost / len(records), 4) if total_cost and records else None, 4
                    ),
                    _fmt(round(median(latencies), 1) if latencies else None, 1),
                    _fmt(round(max(latencies), 1) if latencies else None, 1),
                    _fmt(_upload_mb(records)),
                ]
            )
            + " |"
        )
    return lines


def _upload_mb(records: Sequence[dict[str, Any]]) -> float | None:
    """Mean request bytes per item: model requests plus Base64 ASR audio."""
    sizes = [
        (_num(_stage(record, "model_request_bytes")) or 0.0)
        + (_num(_stage(record, "asr_upload_bytes")) or 0.0)
        for record in records
        if _stage(record, "model_request_bytes") is not None
    ]
    return round(mean(sizes) / 1_000_000, 2) if sizes else None


def _timing_share(records: Sequence[dict[str, Any]]) -> str:
    totals: Counter[str] = Counter()
    for record in records:
        timings = _stage(record, "timings_ms")
        if not isinstance(timings, dict):
            continue
        for name, value in timings.items():
            if name != "run" and isinstance(value, int):
                label = (
                    "asr"
                    if name == "tool:transcribe_audio"
                    else "sampling"
                    if name == "tool:sample_evidence"
                    else "model"
                    if name.startswith("model:")
                    else name
                )
                totals[label] += value
    overall = sum(totals.values())
    if not overall:
        return "–"
    return " / ".join(f"{name} {value / overall:.0%}" for name, value in totals.most_common())


def stage_table(rows: Sequence[SystemRows]) -> list[str]:
    lines = [
        "| System | ASR CER/WER | Frame moment recall | Evidence key points | Output key points | "
        + " | ".join(stage.replace("lost_at_", "lost: ") for stage in LOSS_STAGES)
        + " | Verifier first pass | Repairs | Time split |",
        "|" + "---|" * (9 + len(LOSS_STAGES) - 1),
    ]
    for row in rows:
        if row.kind != "harness":
            continue
        records = list(row.items.values())
        losses: Counter[str] = Counter()
        for record in records:
            counted = _stage(record, "losses")
            if isinstance(counted, dict):
                losses.update({key: int(value) for key, value in counted.items()})
        asr = _mean(
            _num(_stage(record, "asr_cer"))
            if _stage(record, "asr_cer") is not None
            else _num(_stage(record, "asr_wer"))
            for record in records
        )
        first_pass = [
            _stage(record, "verifier_first_passed")
            for record in records
            if _stage(record, "verifier_first_passed") is not None
        ]
        lines.append(
            "| "
            + " | ".join(
                [
                    row.system,
                    _fmt(asr, 3),
                    _fmt(_mean(_num(_stage(r, "frame_moment_recall")) for r in records)),
                    _fmt(_mean(_num(_stage(r, "evidence_key_point_coverage")) for r in records)),
                    _fmt(_mean(_machine(r, "key_point_coverage") for r in records)),
                    *(str(losses.get(stage, 0)) for stage in LOSS_STAGES),
                    _fmt(
                        sum(1 for value in first_pass if value) / len(first_pass)
                        if first_pass
                        else None
                    ),
                    str(sum(int(_stage(r, "repair_rounds") or 0) for r in records)),
                    _timing_share(records),
                ]
            )
            + " |"
        )
    return lines


def _paired(a: SystemRows, b: SystemRows, metric: str) -> tuple[float | None, int]:
    common = sorted(set(a.items) & set(b.items))
    deltas = []
    for item_id in common:
        left = _machine(a.items[item_id], metric)
        right = _machine(b.items[item_id], metric)
        if left is not None and right is not None:
            deltas.append(right - left)
    return (round(mean(deltas), 3) if deltas else None), len(deltas)


def _total_cost(row: SystemRows, item_ids: Iterable[str]) -> float | None:
    costs = [_cost(row.items[item_id]) for item_id in item_ids if item_id in row.items]
    if not costs or any(cost is None for cost in costs):
        return None
    return sum(cost for cost in costs if cost is not None)


def comparison_table(rows: Sequence[SystemRows]) -> list[str]:
    """Every system against the plain harness of the same suite, on common items."""
    lines = [
        "| Suite | Baseline | System | Items | Δ primary | Δ key points | Δ moments | Cost ratio |",
        "|---|---|---|---|---|---|---|---|",
    ]
    by_suite: dict[str, list[SystemRows]] = defaultdict(list)
    for row in rows:
        by_suite[row.suite_id].append(row)
    for suite_id, suite_rows in sorted(by_suite.items()):
        baselines = [
            row for row in suite_rows if row.kind == "harness" and row.system == row.base_system
        ]
        for baseline in baselines:
            for other in suite_rows:
                if other is baseline:
                    continue
                delta, count = _paired(baseline, other, "primary")
                common = set(baseline.items) & set(other.items)
                base_cost = _total_cost(baseline, common)
                other_cost = _total_cost(other, common)
                ratio = (
                    round(other_cost / base_cost, 2)
                    if base_cost and other_cost is not None
                    else None
                )
                points = _paired(baseline, other, "key_point_coverage")[0]
                moments = _paired(baseline, other, "moment_recall")[0]
                lines.append(
                    f"| {suite_id} | {baseline.system} | {other.system} | {count} | "
                    f"{_fmt(delta, 3)} | {_fmt(points, 3)} | {_fmt(moments, 3)} | {_fmt(ratio)} |"
                )
    return lines


def findings(rows: Sequence[SystemRows], human: Sequence[HumanScore]) -> list[str]:
    """Rule-based conclusions with the documented thresholds; mock systems never count."""
    statements: list[str] = []
    by_suite: dict[str, list[SystemRows]] = defaultdict(list)
    for row in rows:
        if row.model != "mock":
            by_suite[row.suite_id].append(row)
    if not by_suite:
        return ["No live system results: mock runs check plumbing only and support no conclusion."]
    for suite_id, suite_rows in sorted(by_suite.items()):
        bases = [r for r in suite_rows if r.kind == "harness" and r.system == r.base_system]
        for base in bases:
            scored = [
                record for record in base.items.values() if _machine(record, "primary") is not None
            ]
            if len(scored) < MIN_ITEMS:
                statements.append(
                    f"{suite_id} / {base.system}: insufficient evidence "
                    f"({len(scored)} scored items, need {MIN_ITEMS})."
                )
                continue
            statements.extend(_stage_findings(suite_id, base, suite_rows))
        natives = [r for r in suite_rows if r.kind == "native"]
        for native in natives:
            for base in bases:
                delta, count = _paired(base, native, "primary")
                if count < MIN_ITEMS or delta is None:
                    continue
                preference = _preference(_human_for(human, native))
                if delta >= MIN_GAIN and (preference is None or preference > 0.5):
                    statements.append(
                        f"{suite_id}: {native.system} beats {base.system} by {delta:+.2f} primary "
                        f"on {count} items"
                        + (f" and wins {preference:.0%} of human comparisons" if preference else "")
                        + ": prefer the native path for this task or adopt what it does better."
                    )
                elif delta <= -MIN_GAIN:
                    statements.append(
                        f"{suite_id}: {base.system} beats {native.system} by {-delta:+.2f} primary "
                        f"on {count} items."
                    )
    return statements or ["No conclusion meets the documented thresholds yet."]


def _stage_findings(suite_id: str, base: SystemRows, suite_rows: Sequence[SystemRows]) -> list[str]:
    records = list(base.items.values())
    losses: Counter[str] = Counter()
    for record in records:
        counted = _stage(record, "losses")
        if isinstance(counted, dict):
            losses.update({key: int(value) for key, value in counted.items()})
    total = sum(losses.values())
    share = {stage: (losses[stage] / total if total else 0.0) for stage in LOSS_STAGES}
    variants = {row.system: row for row in suite_rows if row.base_system == base.system}
    oracle_asr = variants.get(f"{base.system}+oracle-asr")
    oracle_frames = variants.get(f"{base.system}+oracle-frames")
    asr_gain = _paired(base, oracle_asr, "key_point_coverage")[0] if oracle_asr else None
    frame_gain = _paired(base, oracle_frames, "moment_recall")[0] if oracle_frames else None
    asr_error = _mean(
        _num(_stage(r, "asr_cer"))
        if _stage(r, "asr_cer") is not None
        else _num(_stage(r, "asr_wer"))
        for r in records
    )
    frame_recall = _mean(_num(_stage(r, "frame_moment_recall")) for r in records)
    statements: list[str] = []
    prefix = f"{suite_id} / {base.system}"
    if (share["lost_at_asr"] >= LOSS_SHARE and (asr_gain is None or asr_gain >= MIN_GAIN)) or (
        asr_error is not None and asr_error > ASR_ERROR_LIMIT
    ):
        statements.append(
            f"{prefix}: optimise ASR — {share['lost_at_asr']:.0%} of missed key points were lost "
            f"at ASR, error rate {_fmt(asr_error, 3)}, oracle-ASR gain {_fmt(asr_gain, 3)}."
        )
    if share["lost_at_sampling"] >= LOSS_SHARE or (
        frame_recall is not None
        and frame_recall < FRAME_RECALL_LIMIT
        and frame_gain is not None
        and frame_gain >= MIN_GAIN
    ):
        statements.append(
            f"{prefix}: optimise frame sampling — {share['lost_at_sampling']:.0%} of misses lost "
            f"at sampling, frame moment recall {_fmt(frame_recall)}, oracle-frames gain "
            f"{_fmt(frame_gain, 3)}."
        )
    if share["lost_at_synthesis"] >= LOSS_SHARE:
        statements.append(
            f"{prefix}: optimise synthesis (prompt or model) — {share['lost_at_synthesis']:.0%} "
            "of missed key points were in the evidence but not in the output."
        )
    for row in suite_rows:
        if row.kind != "harness" or row.system == base.system or row.system != row.base_system:
            continue
        delta, count = _paired(base, row, "primary")
        common = set(base.items) & set(row.items)
        base_cost, other_cost = _total_cost(base, common), _total_cost(row, common)
        cheap_enough = (
            base_cost is not None
            and other_cost is not None
            and (base_cost == 0 or other_cost / base_cost <= MAX_COST_RATIO)
        )
        if count >= MIN_ITEMS and delta is not None and delta >= MIN_GAIN and cheap_enough:
            statements.append(
                f"{prefix}: swap the synthesis model to {row.model} — {delta:+.2f} primary on "
                f"{count} items at no more than {MAX_COST_RATIO}x the cost."
            )
    return statements


def measured_sampling(
    documents: Sequence[dict[str, Any]],
) -> dict[tuple[str, str], tuple[int, int]]:
    """Frames sampled and tokens per frame per item, from any harness result."""
    measured: dict[tuple[str, str], tuple[int, int]] = {}
    for document in documents:
        if document.get("system_kind") != "harness" or document.get("media_mode") == "fake":
            continue
        for record in document.get("items") or []:
            if not isinstance(record, dict):
                continue
            frames = _num(_stage(record, "frames_sampled"))
            width = _num(_stage(record, "frame_width"))
            height = _num(_stage(record, "frame_height"))
            if frames is not None and width and height:
                key = (str(document.get("suite_id")), str(record.get("item_id")))
                measured[key] = (int(frames), frame_tokens(int(width), int(height)))
    return measured


def estimate_table(
    suites: Sequence[LoadedSuite],
    prices: LoadedEvalPrices,
    systems: Sequence[str],
    measured: dict[tuple[str, str], tuple[int, int]] | None = None,
) -> list[str]:
    lines = [
        f"| Suite | System | Items | Minutes of video | Measured sampling | "
        f"Estimated cost ({prices.table.currency}) |",
        "|---|---|---|---|---|---|",
    ]
    measured = measured or {}
    for loaded in suites:
        durations: list[tuple[float, bool, tuple[int, int] | None]] = []
        for item in loaded.suite.items:
            if item.status == "placeholder":
                continue
            spec = loaded.specs.get(item.item_id)
            duration = (
                item.source.clip.end_seconds - item.source.clip.start_seconds
                if item.source.clip is not None
                else spec.duration_seconds()
                if spec is not None
                else item.source.duration_seconds
            )
            if duration is not None:
                sampled = measured.get((loaded.suite.suite_id, item.item_id))
                durations.append((duration, item.source.has_audio is not False, sampled))
        for name in systems:
            spec_system = parse_system(name)
            if spec_system.mock:
                continue
            amounts = [
                estimate_cost(
                    spec_system.kind,
                    spec_system.model,
                    duration,
                    audio,
                    prices,
                    measured_frames=sampled[0] if sampled else None,
                    tokens_per_frame=sampled[1] if sampled else None,
                )
                for duration, audio, sampled in durations
            ]
            total = (
                round(sum(a for a in amounts if a is not None), 2)
                if amounts and all(a is not None for a in amounts)
                else None
            )
            minutes = round(sum(entry[0] for entry in durations) / 60, 1)
            with_sampling = sum(1 for entry in durations if entry[2] is not None)
            sampling = (
                f"{with_sampling}/{len(durations)}" if spec_system.kind == "harness" else "n/a"
            )
            lines.append(
                f"| {loaded.suite.suite_id} | {name} | {len(durations)} | {minutes} | {sampling} | "
                f"{_fmt(total)} |"
            )
    return lines


def build_report(
    documents: Sequence[dict[str, Any]],
    human: Sequence[HumanScore] = (),
    *,
    suites: Sequence[LoadedSuite] = (),
    prices: LoadedEvalPrices | None = None,
    estimate_systems: Sequence[str] | None = None,
) -> str:
    rows = sorted(group_rows(documents).values(), key=lambda row: (row.suite_id, row.system))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# VidSnap task evaluation report",
        "",
        f"Generated {now} from {len(documents)} result file(s). Machine metrics are "
        "deterministic checks against each item's reference (see docs/eval.md); failed runs "
        "score 0 on the primary metric; '–' means not measurable. Mock systems check plumbing "
        "only.",
        "",
    ]
    for suite_id in sorted({row.suite_id for row in rows}):
        suite_rows = [row for row in rows if row.suite_id == suite_id]
        lines += [f"## {suite_id} ({suite_rows[0].task})", ""]
        lines += overview_table(suite_rows, human)
        lines.append("")
        if any(row.kind == "harness" for row in suite_rows):
            lines += ["Per-stage metrics (harness systems):", ""]
            lines += stage_table(suite_rows)
            lines.append("")
        skipped = {row.system: dict(row.skipped) for row in suite_rows if row.skipped}
        if skipped:
            lines += [f"Skipped items: {json.dumps(skipped, ensure_ascii=False)}", ""]
    if len(rows) > 1:
        lines += ["## Paired comparisons against the plain harness", ""]
        lines += comparison_table(rows)
        lines.append("")
    lines += ["## Findings", ""]
    lines += [f"- {statement}" for statement in findings(rows, human)]
    lines.append("")
    if prices is not None and suites:
        lines += [
            "## Estimated cost of a full run",
            "",
            "Planning estimate from item durations and the assumptions in docs/eval.md; "
            "not a measurement.",
            "",
        ]
        lines += estimate_table(
            suites, prices, estimate_systems or list_systems(), measured_sampling(documents)
        )
        lines.append("")
    return "\n".join(lines)
