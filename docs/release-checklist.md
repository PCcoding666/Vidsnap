# Release Checklist

Release readiness steps for VidSnap: the reusable checks any release must
pass, and the currently recorded verification evidence.

## Reusable release steps

Run the release from a clean checkout in a clean virtual environment. Keys
come only from local environment variables and are needed by no step below;
every check here is offline.

### Source gates

- Clean build: `python -m build` produces the sdist and wheel from a clean
  working tree.
- `ruff format --check src tests scripts`
- `ruff check .`
- `mypy src`
- `python -m pytest -q`
- `vidsnap conformance`
- Secret scan: `python scripts/secret_scan.py`
- `git diff --check`

### Wheel installation and smoke

- Wheel installation: install the built wheel into a brand-new virtual
  environment.
- Package import: `python -c "import vidsnap; print(vidsnap.__file__)"` must
  resolve from that environment's site-packages, not the source tree.
- `vidsnap --help` renders usage.
- `vidsnap conformance` passes from the installed wheel.

### Zero-key offline verification

- Zero-key demo: with both `VIDSNAP_QWEN_API_KEY` and `QWEN_API_KEY` unset,
  `vidsnap demo` replays the packaged demo fixture offline — no network, no
  model call, no private media.
- Trace export: `vidsnap trace export RUN_DIR -o trace.html` produces a fully
  offline HTML trace for the run.

### Plugin and recipe surfaces

- Plugin validate: on a copy of `examples/plugin-template/`,
  `vidsnap plugin validate .` reports the project contract valid.
- Plugin test: `vidsnap plugin test .` on the same copy passes without
  executing the plugin's tool against media.
- Plugin pytest: the copied template's offline test suite passes.
- Offline recipe fixture: the packaged recipe's offline tests pass from the
  installed package.

### Wheel inspection

Inspect the wheel contents (for example `python -m zipfile -l dist/*.whl`):

- JSON schema `vidsnap.video-analysis/v1` present in package data.
- Prompt assets: all prompts (the five JSON prompt assets) ship in the wheel.
- Demo fixture files (provenance, manifest, events, result, evidence) present
  in package data.
- Trace assets (`trace.html`, `timeline.js`) present.
- Recipes and the benchmark trust module present.
- CLI entrypoint registered: `vidsnap = vidsnap.cli:main` in the wheel's
  entry points.

### Documentation checks

- README install: the README install command
  `python -m pip install -e '.[server,dev]'` is documented as running from a
  source checkout.
- Example commands: every example command in the README and docs corresponds
  to a real CLI command (`vidsnap --help` lists them).

### Benchmark claims

Benchmark infrastructure ready; current results are not statistically
meaningful. No live benchmark results are claimed. Do not attach performance,
superiority, quality, latency, or cost claims to a release.

## Current verified evidence

Recorded from a pre-documentation stranger-environment run in the external
directory `/tmp/vidsnap-v01-release.i049cZ` (outside the repository; this is
not a statement about this worktree's final state):

- Clean build: sdist and wheel built.
- Wheel inspection: the wheel contained the JSON schema, all prompts (five),
  11 demo fixture evidence files plus manifest, events, result, and
  provenance, the trace HTML/JS assets, recipes, the benchmark trust module,
  and the console entrypoint `vidsnap = vidsnap.cli:main`.
- Wheel installation into a fresh venv; package import resolved from
  site-packages.
- `vidsnap --help` passed.
- Conformance passed 12 checks.
- Zero-key demo with credentials unset: `vidsnap demo` replayed 6 steps, 2
  tool calls, 11 evidence items, verified 8/8 claims, and exported its trace.
- Plugin validate and plugin test on the copied plugin template returned
  VALID/PASS; its offline pytest was 1 passed.
- The copied offline recipe tests passed: 79 passed.

Final clean source gate (verified, `/tmp/vidsnap-v01-final.MkYXEI`): a new
virtual environment with an editable source install succeeded, then:

- `ruff format --check src tests scripts`: PASS, 158 files already formatted.
- `ruff check .`: PASS.
- `mypy src`: PASS, 72 source files.
- `python -m pytest -q`: PASS, 612 passed (one existing
  `importlib.abc.Traversable` deprecation warning).
- `python -m build`: PASS (sdist and wheel).
- `vidsnap conformance`: PASS, 12 checks.
- `python scripts/secret_scan.py`: PASS.
- `git diff --check`: PASS.

Only the release commit remains pending.

No live provider call was made and no performance, superiority, quality,
latency, or cost claim is recorded. No live benchmark results are claimed.
