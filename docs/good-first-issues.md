# Good First Issues

Small, well-scoped starter tasks for VidSnap. Each card lists the target area, expected outcome, candidate files, acceptance criteria, and explicit non-goals. Pick one card per contribution.

## 1. Plugin template: usage notes and doc test

Outcome: A short README section (or docstring) inside `examples/plugin-template` explaining how a contributor copies the template, renames the plugin, and runs the template's own tests, plus one offline test that asserts the template's documented files exist and its example test passes.

Files: `examples/plugin-template`, `tests/` (one new test file alongside existing offline tests).

Acceptance: `python -m pytest -q` passes with the new test; the documented steps are followed verbatim by the author and work; no production code under `src/vidsnap/` changes.

Non-goals: New plugin APIs, plugin discovery/loading changes, or packaging changes.

## 2. Provider compatibility matrix documentation

Outcome: A compatibility table in `docs/providers.md` listing which provider entries are exercised by the offline suite in `tests/providers`, what each entry requires from local environment variables, and where a contributor adds a new compatibility test.

Files: `docs/providers.md`, `tests/providers`.

Acceptance: Every provider test file under `tests/providers` is represented in the table; the doc states the fixed-model and concurrency rules exactly as enforced in the repo; `ruff format --check .` and `ruff check .` stay clean.

Non-goals: Adding new providers, changing provider ports under `src/vidsnap/`, or altering key handling.

## 3. Interview recipe: deterministic fixtures

Outcome: One or two small deterministic input fixtures for the source-preserving interview recipe in `tests/recipes`, with a test that runs the recipe pipeline against them and asserts stable, ordered outputs, so recipe behavior changes are caught by the offline suite.

Files: `src/vidsnap/recipes`, `tests/recipes`.

Acceptance: The test is fully offline (no network, no model calls), runs in the standard `python -m pytest -q` suite, and uses fixtures committed as small text files; the recipe source is only touched if a genuine bug surfaces.

Non-goals: New recipe stages, prompt changes, or provider/model changes.

## 4. Trace viewer: accessibility pass

Outcome: An accessibility improvement to the viewer's HTML template `src/vidsnap/trace/assets/trace.html` and its exporter `src/vidsnap/trace/export.py` — e.g., document title, landmark roles or heading structure, and text alternatives for any non-text elements — covered by a test in `tests/trace` that asserts the emitted markup contains the expected accessibility attributes.

Files: `src/vidsnap/trace/assets/trace.html`, `src/vidsnap/trace/export.py`, `tests/trace`.

Acceptance: `python -m pytest -q` passes including the new assertion; rendering behavior for existing consumers is unchanged apart from added attributes; the change is limited to markup/output of the viewer.

Non-goals: Interactive widgets, JavaScript frameworks, or a new viewer UI.

## 5. Conformance check reference

Outcome: A reference section in `docs/README.md` listing each check reported by `vidsnap conformance` — loop_spec, prompt_metadata, output_schema, state_machine, forbidden_dependencies, default_model_visible_tools, fixed_default_tool_order, plugin_dependency_graph, trace_template_packaged, trace_schema, fixed_default_policy, and budgets — with a short description of what each check verifies, written from reading `src/vidsnap/conformance.py` rather than assumed behavior.

Files: `docs/README.md`.

Acceptance: All twelve checks are named exactly as they appear in the report output; each description matches the current implementation, so a reviewer can verify every claim against `src/vidsnap/conformance.py`; no code changes.

Non-goals: Changing conformance checks themselves or adding new CLI flags.

## 6. Schema and trace field documentation

Outcome: Documentation in `docs/README.md` (or a linked doc page) describing the purpose of each file under `src/vidsnap/contracts/schemas` and how trace fields emitted by the harness correspond to those schemas, based on reading the current schema files rather than assumed behavior.

Files: `src/vidsnap/contracts/schemas`, `docs/README.md`.

Acceptance: Every schema file under `src/vidsnap/contracts/schemas` is mentioned; field descriptions match the schema contents at time of writing; a reviewer can verify each claim by reading the schema file next to the doc line.

Non-goals: Schema changes, schema versioning policy, or new validation code.
