# Trace format and run index

This page describes what a VidSnap run records, as of version 0.1.1. A run
writes one RunBundle; CLI runs also append one line to a local run index.
Everything here is local: nothing is uploaded, and the localhost API never
writes the run index.

## RunBundle

```text
<bundle>/
  manifest.json     vidsnap.run/v1 manifest; trace_schema is vidsnap.trace/v1
  events.jsonl      append-only event ledger, one JSON event per line
  evidence/         one JSON file per evidence item
  artifacts/        frames and audio extracted from your local video
  result.json       the structured output, when the run produced one
```

`vidsnap analyze` writes the bundle to `--output-dir`, or to a new directory
under the runs root. `vidsnap recipe interview` always keeps its bundle under
the runs root, whatever the outcome, and prints its location as `run_path`.
It refuses a non-empty `--output-dir` before the run starts, so no model call
is spent on output it could not write.
The runs root is `--runs-root`, else `VIDSNAP_RUNS_ROOT`, else `./run`.
A command that needs the runs root creates it before the run starts and
refuses with `runs root not writable: <path>; pass --runs-root` (exit 2) if
it cannot; `analyze --output-dir` still runs and only warns that the index
was not updated. When a recipe run fails, its JSON output includes
`failure_reason` if the reason is one of VidSnap's own fixed reasons.
The bundle directory name is not the run id; the run id is in `manifest.json`
and in the run index.

A kept bundle holds your data: a full-length 16 kHz mono WAV of the video's
audio (about 115 MB per hour), the sampled frame JPEGs, the transcripts, and
the structured result. Delete a bundle folder whenever you no longer need it.
`vidsnap recipe interview --no-keep-bundle` restores the 0.1.0 behavior: a
temporary bundle removed when the command ends, and no index line.

Every event payload passes key-based redaction before it is written: values
under keys containing `api_key`, `authorization`, `credential`, `password`,
`secret`, or `token` are replaced with `***REDACTED***`, except the usage
counters `input_tokens`, `output_tokens`, `prompt_tokens`, `completion_tokens`,
and `total_tokens`, which keep a non-negative integer or `null`.

## What 0.1.1 adds to the ledger

All additions are new payload keys inside existing events, so the trace
schema stays `vidsnap.trace/v1`. Bundles written by 0.1.0, and the packaged
demo fixture, do not have them; readers treat a missing key as unknown.
Unknown values are always `null`, never zero and never guessed.

### Run header: `run.started`

| Key | Meaning |
|---|---|
| `schema_version` | `vidsnap.run-header/v1` |
| `policy` | The policy class name, such as `FixedPolicy` or `AgenticPolicy` (also recorded by 0.1.0) |
| `goal` | The goal objective, exactly as given |
| `required_sections` | The goal's required sections, as given |
| `input_sha256` | SHA-256 of the input file, or `null` if it is not a readable regular file (pipes and devices are never read) |
| `input_size_bytes` | Size of the input file in bytes, or `null` |
| `provider` | `{"id", "model"}` of the model provider, or `null` when unknown |
| `speech_recognizer` | `{"id", "model"}` of the speech recognizer, or `null` when none or unknown |
| `recipe` | `{"id", "version"}` for recipe runs, else `null` |
| `plugins` | `[{"id", "version"}]` of the resolved tool plugins |
| `package_version` | The VidSnap version that ran |

The input is hashed before the run's wall-clock budget starts, so hashing time
is not counted in the run's budget or in its recorded duration. The provider
is known for the built-in Qwen stack and for any port that declares a
`ProviderIdentity`; the redacted provider URL stays in `manifest.json`.
Exported HTML traces never show `provider` or `speech_recognizer`.

The input's duration comes from the probe, which runs after `run.started`. It
is recorded on `probe.completed` (`duration_seconds`, as in 0.1.0) and repeated
on the terminal run event.

### Terminal run event: `run.completed`, `run.failed`, `run.blocked`

| Key | Meaning |
|---|---|
| `terminal_state` | The terminal state (also recorded by 0.1.0) |
| `input_duration_seconds` | Probed input duration, or `null` if the probe never completed |
| `failure` | A `vidsnap.run-failure/v1` record when the run ended with a failure, else `null` |

A run failure record holds `schema_version`, `category`, `http_status`
(or `null`), and `reason`, the same short reason the terminal phase records.
`PARTIAL` and `NO_OP` are outcomes, not failures: their `failure` is `null`
and failed verifier gates are on `verifier.completed`.

### Tool calls: `tool.call.started`

| Key | Meaning |
|---|---|
| `name` | Tool name (also recorded by 0.1.0) |
| `arguments` | The validated arguments the tool received, including schema defaults, after redaction |
| `fingerprint` | The kernel's call fingerprint, used to reject duplicate calls |

The fingerprint is the SHA-256 of the tool name, one `0x1F` byte, and the
validated arguments as compact ASCII JSON with sorted keys, computed before
redaction. It is a one-way digest; redacted values never appear in the
ledger. `tool.call.completed` and `tool.call.failed` keep their 0.1.0 shape.

### Failed model requests: `model.request.failed`, `model.request.blocked`

The payload carries `failure` in the `vidsnap.provider-failure/v1` shape:

| Key | Meaning |
|---|---|
| `schema_version` | `vidsnap.provider-failure/v1` |
| `category` | One of the categories below |
| `http_status` | The HTTP status, when the provider answered with one |
| `input_bytes` | Size of the request body the client built, as compact ASCII JSON; not proof the provider received it |
| `input_tokens`, `output_tokens` | Only when the provider reported them; otherwise `null` |

When a failure carries measurements, the event's `usage` records them with
`model_calls: 1`; `provider_reported` is `true` only when both token counts
were reported. A failure with no measurement keeps `usage: null`.

Custom providers can attach the same record by raising
`ProviderError(message, failure=ProviderFailure(...))`, with `ProviderFailure`
from `vidsnap.contracts`; otherwise the kernel
categorizes by exception type. No exception text, URL, header, key, or
provider response body is ever recorded.

### Failure categories

| Category | Meaning |
|---|---|
| `connect_timeout`, `read_timeout`, `write_timeout`, `pool_timeout` | The HTTP client timed out at that stage |
| `connection_error`, `transport_error` | The connection failed, or another transport error occurred |
| `http_4xx`, `http_5xx`, `http_other` | The provider answered with a non-success status of that class; `http_4xx` includes rejections such as authentication, rate limits, and content moderation |
| `invalid_response` | The provider answered, but not with a usable result |
| `provider_unavailable` | No credential or no model port was configured, so no request was made |
| `provider_error` | Any other provider error that carried no detail |
| `cancelled` | The run or request was cancelled |
| `run_deadline` | The run exceeded its wall-clock budget |
| `budget_exhausted` | The run exceeded another budget: tool calls, model calls, iterations, or evidence frames |
| `validation` | A model-requested tool call or final output failed validation |
| `media_error` | FFmpeg or ffprobe could not read the local media |
| `unknown` | Anything else |

## Run index: `<runs root>/index.jsonl`

Each finished `vidsnap analyze` or `vidsnap recipe interview` run appends one
JSON line with `"schema_version": "vidsnap.run-index/v1"` and
`"record": "run"`. Every field is derived from the finalized bundle, so the
index can be rebuilt from bundles; fields a bundle never recorded are `null`.
If indexing fails, the run's outcome is unchanged and a warning goes to
stderr. Readers skip and count lines they cannot decode or parse, and a new
line always starts after a damaged last line.

| Field | Meaning |
|---|---|
| `run_id`, `started_at`, `finalized_at` | From `manifest.json` |
| `indexed_at` | When the line was written |
| `command` | `analyze` or `recipe interview` |
| `recipe`, `policy`, `goal` | From the run header |
| `input_sha256`, `input_size_bytes`, `input_duration_seconds` | Input identity and probed duration |
| `provider`, `model` | From the run header, else from `manifest.json` |
| `package_version` | `code_version` from `manifest.json` |
| `duration_ms` | Wall time of the run span |
| `model_calls`, `tool_calls` | From the last `budget.updated` snapshot |
| `input_tokens`, `output_tokens` | Token totals over model requests |
| `tokens_reported` | `true` only if every model request reported its usage |
| `cost` | See below; `null` when no price table was supplied |
| `terminal_state` | The outcome the command reported |
| `bundle_terminal_state` | The bundle's own terminal state; it differs from `terminal_state` only when the command failed after the run finished, for example when the recipe could not write its output, and then `failure_reason` is the command's reason |
| `failed_gates` | Failed verifier gates, `[]` if all passed, `null` if never verified |
| `failure_category`, `http_status`, `failure_reason` | From the run failure record |
| `bundle_path` | Absolute path of the bundle |

Token totals cover model requests only. Speech recognition runs inside a
tool, and the built-in recognizer reports no usage, so its cost is not in
these totals.

`vidsnap runs review RUN` appends a `"record": "review"` line for an indexed
run, where `RUN` is a run id, a unique prefix of at least four characters, or
a bundle path:

| Field | Meaning |
|---|---|
| `run_id`, `reviewed_at` | Which run, and when the review was written |
| `edit_minutes` | `--edit-minutes`: minutes spent editing the output |
| `published` | `--published` or `--not-published` |
| `factual_errors` | `--factual-errors`: factual errors found |
| `images_replaced` | `--images-replaced`: images replaced by hand |
| `note` | `--note`: free text |

Fields left out stay `null`; at least one is required. A later review of the
same run does not overwrite an earlier one; `vidsnap runs list` shows the
latest. `vidsnap runs list` prints every indexed run as a table; a `?` after
the token counts means some model request did not report its usage.

## Cost and price tables

VidSnap ships no prices. Cost is recorded only when you supply a price table
with `--price-table` or `VIDSNAP_PRICE_TABLE`, in this shape (illustrative
names and numbers; use your provider's current price list):

```json
{
  "schema_version": "vidsnap.price-table/v1",
  "currency": "CNY",
  "models": {
    "example-model": {"input_per_million_tokens": 1.0, "output_per_million_tokens": 2.0}
  }
}
```

An invalid table is refused before the run starts. With a valid table, the
index line's `cost` is
`{"amount", "currency", "model", "complete", "note", "price_table_sha256"}`.
`amount` is computed only when the run's model is known, is listed in the
table, and every model request reported its usage; otherwise `amount` is
`null`, `complete` is `false`, and `note` is `model_unknown`,
`model_not_in_price_table`, or `usage_not_reported`.
