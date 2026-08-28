# Providers

VidSnap keeps every model call behind typed provider ports. A provider is the
single place where your application talks to a model; the bounded harness loop,
the verifier, and the tool ports never see a raw client, an endpoint, or a
credential.

Two built-in providers ship with the package: `QwenProvider` for live runs
against the approved Qwen endpoint and `MockProvider` for offline work.
Anything that satisfies the runtime `ProviderProtocol` contract can be injected
instead.

## The provider boundary

The application chooses one provider before a run. The provider object is
passed in at construction time, and from that point on it is fixed. The agent
cannot choose or switch provider/model/base_url during a run. This is enforced
structurally: the request objects the provider receives
(`AgentStepRequest`) and the decisions it returns (`AgentDecision`,
`ToolPlan`) carry no provider, model, or base_url fields, so there is nothing
for a model response to influence even in principle.

```python
from vidsnap.providers import MockProvider
from vidsnap.harness import VideoHarness

harness = VideoHarness(provider=MockProvider())
# provider is now wired into the model, planner, and agent-model ports
```

`VideoHarness` accepts either `provider=` or the lower-level `model=` /
`planner=` ports, never both at once. Passing both raises `ValueError`. A
provider does not supply speech recognition; pass `recognizer=` explicitly or
audio transcription is skipped for that run.

## ProviderProtocol and ProviderIdentity

`ProviderProtocol` is a `typing.Protocol` (runtime checkable) that merges the
three model ports plus one read-only identity:

```python
from vidsnap.providers import ProviderIdentity, ProviderProtocol

class ProviderProtocol(AgentModelPort, ToolPlanningPort, VideoModelPort, Protocol):
    @property
    def identity(self) -> ProviderIdentity: ...
```

A complete provider must implement:

| Method | Purpose |
| --- | --- |
| `analyze_evidence(evidence, goal) -> ModelResponse` | Produce a schema-valid result for typed, captured evidence. |
| `plan_tools(probe, goal) -> ToolPlanResponse` | Choose a bounded subset of `transcribe_audio` / `sample_evidence`. |
| `decide_next(request) -> AgentDecisionResponse` | Return exactly one bounded tool-call batch or one final answer. |
| `identity` (read-only property) | The fixed `ProviderIdentity` used by discovery, selection, and audit. |

`ProviderIdentity` is a frozen dataclass with three fields: `id`, `model`, and
`base_url`. Each `ProviderIdentity` value is immutable once constructed, and the
application keeps the run-selected identity to record which provider served a
run.

## Built-in providers

### QwenProvider

QwenProvider is the reference provider. It subclasses `QwenCompatibleClient`,
which speaks the OpenAI-compatible chat-completions protocol against the
single approved endpoint, with a semaphore capping model concurrency at two.
It reads only the typed inputs each port receives, never accepts a
caller-selected model or URL, and sends evidence images only as base64 data
URLs (JPEG, PNG, or WebP, at most 5 MB each).

```python
import os
from vidsnap.providers import QwenProvider
from vidsnap.harness import VideoHarness

provider = QwenProvider(api_key=os.environ["VIDSNAP_QWEN_API_KEY"])
harness = VideoHarness(provider=provider)
result = await harness.run(source, goal)
```

The key comes only from local environment variables (`VIDSNAP_QWEN_API_KEY`
or `QWEN_API_KEY`). Without a key, every port raises `ProviderUnavailable`,
which the harness maps to a truthful `BLOCKED` terminal state. A live model
response that is not a valid structured result raises `ProviderError` or
`AgentDecisionFormatError`, mapped to `FAILED`.

### MockProvider

MockProvider is deterministic offline. It takes no configuration, depends on
nothing, and ignores every model input: `analyze_evidence` always returns
`VideoAnalysisResult(summary="mock", claims=[])`, `plan_tools` picks
`transcribe_audio` only when the probe reports audio, and `decide_next`
always returns one final answer. Its identity is
`ProviderIdentity(id="mock", model="mock", base_url="offline://mock")`.

```python
import asyncio
from vidsnap.providers import MockProvider, assert_provider_contract

async def main() -> None:
    await assert_provider_contract(MockProvider())

asyncio.run(main())
```

## Conformance checking

`assert_provider_contract` in `vidsnap.providers.testing` (also exported from
`vidsnap.providers`) is a deterministic, async conformance probe. It checks
that the object satisfies the runtime `ProviderProtocol`, that its identity is
a fully populated `ProviderIdentity`, and that all three ports return the
typed response objects with non-negative usage counters. The helper itself
uses fixed in-memory fixtures and contains no network logic, but the provider
methods it calls may perform network requests; use `MockProvider` or a fake
transport for offline tests.

```python
from vidsnap.providers import MockProvider, assert_provider_contract

async def test_my_provider_conforms() -> None:
    await assert_provider_contract(MyProvider())
```

A failing check raises `AssertionError` with the offending property. Run it in
your own test suite before shipping a provider.

## Injecting providers

### VideoHarness

```python
from vidsnap.providers import MockProvider
from vidsnap.harness import VideoHarness

provider = MockProvider()
harness = VideoHarness(provider=provider)

assert harness.model is provider        # VideoModelPort
assert harness.planner is provider      # ToolPlanningPort
assert harness.agent_model is provider  # AgentModelPort
```

`provider=` is mutually exclusive with `model=` and `planner=`; combining them
raises `ValueError` so a run can never mix two model stacks.

### InterviewRecipeRunner

```python
from vidsnap.providers import MockProvider
from vidsnap.recipes import InterviewRecipeRunner

runner = InterviewRecipeRunner(provider=MockProvider())
result = await runner.run(source, output_dir)
```

The runner wires the provider in as its `agent_model`. `provider=` and
`agent_model=` are mutually exclusive for the same reason. The recipe's goal,
budgets, and tool registry stay fixed recipe constants regardless of which
provider is injected.

## Entry-point discovery

Provider entry points use an explicit allow-list. Third-party packages
advertise a zero-argument factory in the `vidsnap.providers` entry-point
group:

```toml
# in the provider package's pyproject.toml
[project.entry-points."vidsnap.providers"]
mock = "vidsnap.providers.mock:MockProvider"
```

Your application then names exactly which entry points may load:

```python
from vidsnap.providers import PROVIDER_ENTRY_POINT_GROUP, discover_allowed_providers

providers = discover_allowed_providers(["mock"])
# group is PROVIDER_ENTRY_POINT_GROUP == "vidsnap.providers"
```

Discovery loads only entry points whose name appears in the allow-list,
preserves entry-point order, and validates each candidate:

- the factory must be callable with zero arguments;
- the instance must satisfy the runtime `ProviderProtocol`;
- the identity must be a valid `ProviderIdentity` with non-empty
  `id`, `model`, and `base_url`;
- `identity.id` must equal the entry-point name.

Any violation raises `ValueError` naming the entry point. Discovery never
invokes a model port: no prompts are sent while listing providers.

## Trust model

Provider plugins are trusted code, not sandboxed content. Loading a provider
entry point executes the provider package's import-time code with your
application's full privileges, and a provider sees every typed request the
harness sends. The allow-list is an explicit selection mechanism that you
control, not a security boundary; audit a provider package before listing it.

Credentials are the one thing a provider identity may never carry. Custom
provider identities must not contain credentials: `id`, `model`, and
`base_url` name a provider, and secrets belong only in local environment
variables. The no-credentials guarantee covers built-in providers only; it
does not extend to third-party provider plugins, which are trusted code you
audit — the allow-list expresses your selection, not a credential-free
property.

Providers are also a separate extension axis from bounded tool plugins. Tool
plugins extend what evidence the loop may gather and are constrained by the
loop spec's allow-list; providers extend which model serves the three typed
ports. The two axes do not grant each other's capabilities: a provider can
never add tools, change budgets, or alter verifier rules, and a tool plugin
can never choose a model.

## Auditing and redaction

Provider-injected runs record their provider in the `RunBundle` manifest:
`id`, `model`, and `base_url`; legacy runs retain the legacy metadata
behavior. The URL is redacted before storage — `redact_provider_url`
preserves the scheme, host, port, and path while dropping userinfo, query
values, and fragments. Built-in providers keep credentials out of bundles: the
API key lives only in the provider client for the duration of a request, event
payloads are passed through key-based redaction before being appended to
`events.jsonl`, and no database or remote store is involved.

## What providers do not do

- Providers cannot change the model, endpoint, prompts, budgets, verifier, or
  terminal rules mid-run.
- BenchmarkProfile remains locked to qwen3.8-max, so benchmark evidence is
  always produced by the reference model even when other providers exist for
  application runs.
- Provider injection does not include speech recognition; ASR is a separate
  port you pass explicitly.
