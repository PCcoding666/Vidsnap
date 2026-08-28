# plugin-template: a VidSnap tool plugin in 30 minutes

This template is a complete, working VidSnap tool plugin. `video_metadata` is
deterministic: it reads only the `MediaProbe` the harness already computed and
returns seven metadata fields. No model calls, no media I/O, no artifacts.

## Layout

```
plugin-template/
├── pyproject.toml          # package + entry point
├── vidsnap.plugin.json     # static project manifest (validated, never executed)
├── src/video_metadata/     # plugin package: __init__.py, plugin.py
├── tests/test_plugin.py    # offline pytest
├── example_run/probe.json  # sample MediaProbe input fixture
└── example_run/expected_result.json  # structured ToolResult fixture
```

## 1. Copy and rename (5 min)

Copy the whole directory, then rename three things consistently:

1. Package directory `src/video_metadata/` -> `src/your_plugin/`.
2. In `pyproject.toml`: `name`, the hatch `packages` path, and the entry point
   under `[project.entry-points."vidsnap.plugins"]`, e.g.
   `your-plugin = "your_plugin.plugin:TOOL"`. The factory must stay zero-argument
   and be named `TOOL`; it returns a runtime `ToolPlugin`.
3. In `vidsnap.plugin.json`: `id` (lowercase, `^[a-z][a-z0-9_.-]*$`), `name`,
   `version` (`\d+\.\d+\.\d+`), and `capabilities`.

Keep `dependencies = ["vidsnap-harness>=0.1.0"]` so the typed contracts stay in
lockstep with the installed harness.

## 2. Manifest fields (`vidsnap.plugin.json`)

| Field | Meaning |
| --- | --- |
| `api_version` | Manifest dialect, currently `vidsnap.plugin-project/v1`. |
| `id` | Stable project identifier; must match the entry point name. |
| `name` | Human-readable display name. |
| `version` | Semver of the plugin itself. |
| `kind` | Plugin kind; the v1 project contract currently accepts only `tool`. |
| `capabilities.provides` | Capability names this plugin contributes. |
| `capabilities.requires` | Capability names this plugin needs from others. |
| `input_schema` | JSON Schema for the tool arguments; `additionalProperties: false`. |
| `output_schema` | Fixed reference to `vidsnap://schemas/tool-result/v1`. |
| `permissions` | Declared local capability scope, e.g. `read_media_metadata`. |
| `budget_impact` | Declared per-call cost contribution (`tool_calls: 1` here). |
| `entry_point` | Entry point name the loader resolves in the installed distribution. |

## 3. Install (5 min)

From the template directory:

```
python -m pip install -e .
```

Editable install keeps your edits live. `pip show video-metadata` confirms it.

## 4. Static validation (2 min)

```
vidsnap plugin validate .
```

This checks `pyproject.toml` and `vidsnap.plugin.json` only. It never imports or
executes plugin code. Fix every reported mismatch before continuing.

## 5. Installed plugin test (3 min)

```
vidsnap plugin test .
```

This imports the exact allow-listed entry point (`your_plugin.plugin:TOOL`) from
the installed distribution and calls its zero-argument factory to check the
returned object, but it never calls `ToolPlugin.execute`. It confirms the module
imports, the factory exists, and the returned object satisfies the plugin
contract. Runtime behavior is exercised by the offline suite below.

## 6. Offline pytest (5 min)

Run pytest with both import roots on `PYTHONPATH`: the VidSnap repository `src/`
directory and this template's `src/` directory. From the repository root:

```
PYTHONPATH="$PWD/src:$PWD/examples/plugin-template/src" python -m pytest examples/plugin-template/tests -q
```

The test builds a real `ToolExecutionContext` (`MediaProbe`, `AdaptiveSampler`,
typed placeholders for unused ports), calls the `TOOL` factory twice with the
empty input model, and asserts:

- both results are equal (deterministic),
- `result.model_dump(mode="json")` equals `example_run/expected_result.json`,
- no artifact directory was created (no side effects).

## 7. How the example works (5 min)

`plugin.py` contains exactly three pieces:

- `VideoMetadataInput(StrictModel)` — an empty, strict arguments model
  (`extra="forbid"`); the tool takes nothing from the model.
- `_VideoMetadataPlugin` — holds the runtime `PluginManifest` (`kind="tool"`,
  `model_visible=True`), the `name` (`video_metadata`), the `input_model`, and
  `execute(arguments, context)`, which reads only `context.probe` and returns a
  `completed` `ToolResult` with no evidence IDs, `ProviderUsage(reported=False)`,
  and a summary of `duration_seconds`, `fps`, `width`, `height`, `has_audio`,
  `video_codec`, `audio_codec`.
- `TOOL()` — the zero-argument factory the entry point resolves.

The structured content of `expected_result.json` must exactly equal
`result.model_dump(mode="json")` for `probe.json`. Regenerate it whenever you
change the summary shape.

## 8. Adapt it (5 min)

- More inputs: add typed, constrained fields to your `StrictModel`; mirror them
  in `input_schema` with `additionalProperties: false`.
- More capabilities: use other bounded context members (`context.media`,
  `context.sampler`, `context.evidence_sink` via the sink API, `context.recognizer`
  when present). Allocate and store evidence only through `evidence_sink`.
- New outputs: keep `summary` values JSON-compatible (`JsonValue`); extend
  `expected_result.json` and the test in the same change.
- Update `permissions` and `budget_impact` in the manifest to match reality.

## Trust and invocation model

Installed plugin Python is trusted code, not a sandbox: it runs with the full
permissions of your host process, so only install code you trust.

- `vidsnap plugin validate .` never imports or executes plugin code.
- `vidsnap plugin test .` imports the exact allow-listed entry point and calls
  its zero-argument factory, but it never calls `ToolPlugin.execute`.
- The Agent uses tools only through a typed, bounded `ToolExecutionContext`
  scoped to one local source. The static `permissions` and `budget_impact`
  declarations cannot dynamically expand the harness policy or budget.
