# Benchmark methodology

This document specifies the deterministic, offline trust evaluation implemented
in `src/vidsnap/benchmark/trust.py`. It defines how Direct and Harness runs are
compared fairly and what the nine metrics mean. It publishes no result: every
number below is a formula, never a measurement.

## Fair Direct-vs-Harness registration

- Each registered case fixes provenance that every outcome must repeat
  unchanged: `case_id`, `source_sha256`, `input_fingerprint`,
  `transcript_condition`, `transcript_fingerprint`, `model`, `dataset`,
  `dataset_version`, and `available_evidence_fingerprint`.
- `declared_evidence_fingerprints` must include the available evidence
  fingerprint. Outcomes may use only declared evidence, and this restriction
  applies to Direct and Harness identically.
- The manifest is sealed: `manifest_sha256` is the SHA-256 of the canonical
  JSON (sorted keys, compact separators, UTF-8) of exactly `registered_cases`
  and `variants`. Evaluation recomputes the seal and rejects a stale or mutated
  manifest; a supplied seal is only format-checked, never trusted.
- Coverage is exact: there must be exactly one outcome for every registered
  case×variant pair. Duplicates, missing outcomes, and extra outcomes are all
  rejected, so cherry-picking after registration is impossible.

## The nine metrics

All metrics are computed per variant over the same registered cases in the same
order. Missing observations are unknown, never zero: an unknown metric reports
`status="unknown"` with null `value`, `numerator`, and `total`, and
`denominator=0`. A count-ratio metric is eligible for a record only when its
measurement records both the numerator and the denominator field; a per-record
`numerator` greater than its `denominator` is rejected. Ratios aggregate as the
summed numerator over the summed denominator.

- **Temporal Grounding** — every recorded observation pair
  `((pred_start, pred_end), (ref_start, ref_end))` is scored with the
  intersection-over-union (IoU) of the two intervals. The value is the mean IoU
  and the denominator is the number of observation pairs. No observations means
  unknown.
- **Citation Precision** — numerator is Σ `citations_resolved`, denominator is
  Σ `citations_total`. If eligible records exist but the summed denominator is
  0, the value is 1.0 (measured).
- **Unsupported Claim Rate** — numerator is Σ `claims_unsupported`, denominator
  is Σ `claims_total`. An empty summed denominator with eligible records gives
  0.0.
- **Evidence Coverage** — numerator is Σ `claims_with_evidence`, denominator is
  Σ `claims_total`. An empty summed denominator with eligible records gives 1.0.
- **Tool Budget Compliance** — a record is eligible only when all three caps
  (`max_model_calls`, `max_tool_calls`, `max_evidence_frames`) and all three
  usages (`model_calls`, `tool_calls`, `evidence_frames`) are recorded. An
  outcome is compliant when all three usages stay within their caps. The value
  is compliant outcomes over eligible outcomes.
- **Provider Regression** — a record is eligible only when the case declares
  `baseline_result_fingerprint` and the measurement records a
  `result_fingerprint`. The value is fingerprint mismatches over eligible
  outcomes.
- **Latency** — the value is the median of recorded `latency_seconds`; `total`
  is the sum and the denominator is the count. No values means unknown.
- **Cost** — the value is the median of recorded `cost_usd`; `total` is the sum
  and the denominator is the count. No values means unknown.
- **Replay Determinism** — a record is eligible only with at least two
  repetitions; it is deterministic when every repetition matches the first on
  both `result_fingerprint` and `trace_fingerprint`. The value is deterministic
  outcomes over eligible outcomes.

## Offline evaluation command

    vidsnap benchmark evaluate INPUT_JSON --output REPORT_JSON

- INPUT_JSON must contain exactly the strict top-level keys `manifest` and
  `outcomes`; any extra key is rejected.
- Evaluation is pure offline: no provider key, no provider configuration, no
  network or socket access.
- REPORT_JSON is written only after parsing, validation, and evaluation all
  succeed, so a failed run leaves no output file.
- The report is deterministic: sorted-key compact UTF-8 JSON with a single
  trailing newline, byte-identical for identical input, with a stable
  `report_sha256` computed over the report content excluding the hash itself.

Status: benchmark infrastructure ready; current results are not statistically meaningful.

## Published claims

No live result, no superiority, no quality, no latency, and no cost claims are
published. The infrastructure and its contracts exist; measurements do not.
