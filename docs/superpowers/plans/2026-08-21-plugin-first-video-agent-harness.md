# Plugin-first Video Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前一次性 ToolPlan 流水线改造成插件优先、可多轮调用工具、自动记录真实轨迹的 Video Agent Harness，同时保持 Fixed 默认行为兼容。

**Architecture:** 新增严格插件契约、统一 HarnessKernel、Fixed/Agentic/Direct 三种执行策略、任务适配器与 append-only trace schema。`VideoHarness` 退化为默认组件装配器；benchmark 复用同一内核；静态轨迹查看器只读取真实 RunBundle 事件。

**Tech Stack:** Python 3.10+、Pydantic 2、asyncio、httpx、Typer、FFmpeg/ffprobe、pytest/pytest-asyncio、Ruff、Mypy、Hatchling。

**Spec:** `docs/superpowers/specs/2026-08-21-plugin-first-video-agent-harness-design.md`

## Global Constraints

- 默认推理模型固定为 `qwen3.8-max`；内部 benchmark 包括 ASR 在内的所有模型调用都固定为 `qwen3.8-max`。
- 默认及 benchmark 的模型可见工具严格限制为 `transcribe_audio` 与 `sample_evidence`。
- 模型不能选择模型、endpoint、URL、prompt、预算、verifier、插件装载或终态。
- `HarnessPolicy.tool_mode` 默认继续为 `fixed`；Fixed 不增加 planner call，顺序继续为 ASR → visual → final model → verifier。
- 继续保留最多 12 次模型调用、96 帧模型选择证据、900 秒墙钟限制；新增最多 6 次模型可见工具调用。benchmark-only Direct 继续完整使用注册的 `fps=2` 帧序列（现有 smoke 可达约 147 帧），不把它误计为模型选择的 96 帧预算，但必须记录真实帧数并受外部预注册 case/输入协议约束。
- 不保存 API Key、Authorization、原始 provider request/response、隐藏推理、完整 transcript 或图片 data URI 到事件、报告或 HTML。
- 不恢复 SaaS 前端、账号、数据库、任务历史、Redis、Celery、WebSocket 或计费。
- 不扩大 benchmark 数据集，不运行 live smoke 或 54-case formal；本计划只运行离线 fake-provider 测试。
- 每个任务都按 RED → GREEN → focused regression → commit 执行；不得在同一提交夹带无关重构。
- 实现完成后只形成默认工具与可选数据清单，新增项必须由用户另行审阅批准。

---

## File Map

### 新增

- `src/vidsnap/contracts/agent.py`：AgentDecision、ToolCallRequest、ProviderUsage。
- `src/vidsnap/loop/trace_recorder.py`：model/tool span 配对、真实 duration 与 correlation ID。
- `src/vidsnap/plugins/manifest.py`：`vidsnap.plugin/v1` manifest。
- `src/vidsnap/plugins/base.py`：ToolPlugin、ToolExecutionContext、ToolResult、EvidenceSink、带 usage 的转写端口适配。
- `src/vidsnap/plugins/registry.py`：依赖校验、allow-list、稳定装载顺序。
- `src/vidsnap/plugins/discovery.py`：受 allow-list 控制的 `vidsnap.plugins` entry-point 发现。
- `src/vidsnap/plugins/builtin/transcribe_audio.py`：受限时间窗 ASR 插件。
- `src/vidsnap/plugins/builtin/sample_evidence.py`：受限时间窗视觉采样插件。
- `src/vidsnap/plugins/builtin/__init__.py`：默认两工具装配。
- `src/vidsnap/runtime/context.py`：单 run 状态与 EvidenceSink 实现。
- `src/vidsnap/runtime/kernel.py`：不可绕过的 probe、预算、事件、工具执行、验证与终止。
- `src/vidsnap/runtime/policies.py`：FixedPolicy、AgenticPolicy、DirectPolicy。
- `src/vidsnap/runtime/__init__.py`：稳定 runtime 导出。
- `src/vidsnap/tasks/base.py`：TaskAdapter 与 TaskVerification 契约。
- `src/vidsnap/tasks/video_analysis.py`：现有 VideoAnalysisResult 适配器。
- `src/vidsnap/tasks/__init__.py`：任务适配器导出。
- `src/vidsnap/benchmark/adapters.py`：MCQTaskAdapter 与 VariantOutcome 投影。
- `src/vidsnap/trace/models.py`：TraceDocument、TraceLane、TraceItem。
- `src/vidsnap/trace/reader.py`：新旧 RunBundle 读取与 summary-only 标记。
- `src/vidsnap/trace/export.py`：脱敏、自包含静态 HTML 导出。
- `src/vidsnap/trace/assets/trace.html`：无网络请求的轨迹模板。
- `src/vidsnap/trace/__init__.py`：trace API 导出。
- `tests/contracts/test_agent_decision.py`
- `tests/plugins/test_registry.py`
- `tests/plugins/test_builtin_tools.py`
- `tests/runtime/test_fixed_policy.py`
- `tests/runtime/test_agentic_policy.py`
- `tests/runtime/test_policy_security.py`
- `tests/runtime/fakes.py`：Fixed/Agentic 共用的确定性 fake ports、scripted model 与事件读取 helper。
- `tests/tasks/test_video_analysis.py`
- `tests/trace/conftest.py`：新 trace 与 legacy summary-only fixtures。
- `tests/trace/test_reader.py`
- `tests/trace/test_export.py`
- `docs/default-tools-and-data-review.md`：完成后交给用户审阅的清单，不预先新增能力。

### 修改

- `src/vidsnap/contracts/models.py`、`loopspec.py`、`__init__.py`：新增工具调用预算与契约导出。
- `src/vidsnap/loop/events.py`、`run_bundle.py`、`state_machine.py`：加法式 trace 字段和工具预算。
- `src/vidsnap/providers/base.py`、`qwen.py`：标准 AgentStepRequest/AgentDecisionResponse，保留旧接口过渡。
- `src/vidsnap/video/ports.py`、`probe.py`：支持受限音频时间窗。
- `src/vidsnap/harness.py`：改为装配并调用 HarnessKernel。
- `src/vidsnap/skills/base.py`、`builtin.py`：成为 PluginRegistry 的兼容 facade。
- `src/vidsnap/benchmark/live.py`、`scripts/run_agentic_benchmark.py`：三变体走统一内核。
- `src/vidsnap/cli.py`、`pyproject.toml`：增加 `vidsnap trace export` 并打包模板。
- `src/vidsnap/conformance.py`、`README.md`、`docs/README.md`、`docs/migration-to-harness.md`：更新公开契约和发布门槛。

---

### Task 1: Agent 决策与工具调用预算契约

**Files:**
- Create: `src/vidsnap/contracts/agent.py`
- Create: `tests/contracts/test_agent_decision.py`
- Modify: `src/vidsnap/contracts/models.py:44-52`
- Modify: `src/vidsnap/contracts/loopspec.py:23-30`
- Modify: `src/vidsnap/contracts/__init__.py`
- Modify: `tests/contracts/test_models.py`
- Modify: `tests/contracts/test_loopspec.py`

**Interfaces:**
- Produces: `ToolCallRequest`, `AgentDecision`, `ProviderUsage`, `HarnessPolicy.max_tool_calls`, `LoopBudgets.max_tool_calls`。
- Consumes: 现有 `StrictModel` 与 Pydantic `JsonValue`。

- [ ] **Step 1: 写 AgentDecision 失败测试**

```python
def test_agent_decision_requires_exactly_one_branch() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(kind="tool_calls", calls=(), output=None)
    with pytest.raises(ValidationError):
        AgentDecision(kind="final", calls=(ToolCallRequest(name="x"),), output={"x": 1})


def test_agent_decision_allows_at_most_two_calls_and_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({
            "kind": "tool_calls",
            "calls": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
        })
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({"kind": "final", "output": {}, "model": "other"})
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/contracts/test_agent_decision.py -q`

Expected: FAIL with `ModuleNotFoundError: vidsnap.contracts.agent`。

- [ ] **Step 3: 实现严格契约与预算字段**

```python
class ToolCallRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class AgentDecision(StrictModel):
    kind: Literal["tool_calls", "final"]
    calls: tuple[ToolCallRequest, ...] = Field(default=(), max_length=2)
    output: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def require_one_branch(self) -> AgentDecision:
        if self.kind == "tool_calls" and (not self.calls or self.output is not None):
            raise ValueError("tool_calls requires calls and forbids output")
        if self.kind == "final" and (self.calls or self.output is None):
            raise ValueError("final requires output and forbids calls")
        return self


class ProviderUsage(StrictModel):
    input_bytes: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reported: bool = True
```

Add `max_tool_calls: int = Field(default=6, ge=0, le=6)` to both policy models and update the frozen LoopSpec digest assertion to the newly computed digest.

- [ ] **Step 4: 运行契约测试并确认 GREEN**

Run: `.venv/bin/python -m pytest tests/contracts/test_agent_decision.py tests/contracts/test_models.py tests/contracts/test_loopspec.py -q`

Expected: all listed tests PASS。

- [ ] **Step 5: 提交**

```bash
git add src/vidsnap/contracts tests/contracts
git commit -m "feat: add bounded agent decision contracts"
```

---

### Task 2: 加法式真实事件与 span 配对

**Files:**
- Create: `src/vidsnap/loop/trace_recorder.py`
- Modify: `src/vidsnap/loop/events.py:13-37`
- Modify: `src/vidsnap/loop/run_bundle.py:100-157`
- Modify: `tests/loop/test_events.py`
- Modify: `tests/loop/test_run_bundle.py`

**Interfaces:**
- Consumes: `ProviderUsage`。
- Produces: `EventUsage`, extended `RunEvent`, `TraceSpan`, `TraceRecorder.start(...)`, `TraceRecorder.finish(...)`。

- [ ] **Step 1: 写事件配对与脱敏失败测试**

```python
def test_trace_recorder_pairs_real_start_and_completion(tmp_path) -> None:
    bundle = RunBundle.create(tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1")
    recorder = TraceRecorder(bundle, clock=iter((10.0, 10.25)).__next__)
    span = recorder.start("tool.call", phase="sample_evidence", turn=1, step=2, payload={"name": "sample_evidence"})
    completed = recorder.finish(span, status="completed", usage=ProviderUsage(input_bytes=8))
    assert completed.correlation_id == span.correlation_id
    assert completed.duration_ms == 250
    assert completed.event_type == "tool.call.completed"


def test_run_manifest_declares_trace_schema_without_changing_run_version(tmp_path) -> None:
    bundle = RunBundle.create(tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1")
    manifest = json.loads((bundle.path / "manifest.json").read_text())
    assert manifest["api_version"] == "vidsnap.run/v1"
    assert manifest["trace_schema"] == "vidsnap.trace/v1"
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/loop/test_events.py tests/loop/test_run_bundle.py -q`

Expected: FAIL because trace fields and `TraceRecorder` do not exist。

- [ ] **Step 3: 扩展 RunEvent，保留旧字段**

```python
EventStatus = Literal["started", "completed", "failed", "blocked", "skipped"]


class EventUsage(StrictModel):
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    evidence_frames: int = Field(default=0, ge=0)
    input_bytes: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    provider_reported: bool = True
```

Add optional `event_id`, `event_type`, `turn`, `step`, `parent_event_id`, `correlation_id`, `monotonic_offset_ms`, `status`, `usage`, and `duration_ms` fields to `RunEvent`; `phase` and `occurred_at` remain required for old readers.

- [ ] **Step 4: 实现 TraceRecorder 与 RunBundle 扩展参数**

`TraceRecorder.start(base_type, ...)` writes `<base_type>.started` and returns a `TraceSpan`; `finish(span, status, phase=None, ...)` writes `<base_type>.<status>`, copies correlation/parent/turn/step, optionally uses a compatibility phase such as `terminal`, and calculates duration only from the injected monotonic clock. `RunBundle.append_event(...)` redacts the payload before model construction and adds `trace_schema` to the manifest.

- [ ] **Step 5: 运行事件回归并确认 GREEN**

Run: `.venv/bin/python -m pytest tests/loop/test_events.py tests/loop/test_run_bundle.py -q`

Expected: PASS, including existing numeric usage redaction test。

- [ ] **Step 6: 提交**

```bash
git add src/vidsnap/loop tests/loop
git commit -m "feat: record paired harness trace events"
```

---

### Task 3: 插件 manifest、注册表和受控发现

**Files:**
- Create: `src/vidsnap/plugins/__init__.py`
- Create: `src/vidsnap/plugins/manifest.py`
- Create: `src/vidsnap/plugins/base.py`
- Create: `src/vidsnap/plugins/registry.py`
- Create: `src/vidsnap/plugins/discovery.py`
- Create: `tests/plugins/test_registry.py`
- Modify: `src/vidsnap/skills/base.py`
- Modify: `src/vidsnap/skills/builtin.py`
- Modify: `tests/skills/test_builtin_skills.py`

**Interfaces:**
- Consumes: `StrictModel`, `Evidence`, `MediaProbe`, existing media/recognizer/sampler ports。
- Produces: `PluginManifest`, `ToolPlugin`, `ToolExecutionContext`, `ToolResult`, `PluginRegistry`, `discover_allowed_plugins(...)`。

- [ ] **Step 1: 写注册与安全边界失败测试**

```python
@dataclass
class FakePlugin:
    manifest: PluginManifest
    name: str
    input_model: type[StrictModel] = StrictModel

    def __init__(
        self,
        plugin_id: str,
        *,
        provides: tuple[str, ...] = (),
        requires: tuple[str, ...] = (),
    ) -> None:
        self.name = plugin_id.rsplit(".", 1)[-1]
        self.manifest = PluginManifest(
            id=plugin_id,
            version="1.0.0",
            kind="tool",
            provides=provides,
            requires=requires,
            model_visible=True,
        )

    async def execute(self, arguments, context) -> ToolResult:
        del arguments, context
        return ToolResult(status="completed")


class FakeEntryPoint:
    def __init__(self, plugin: FakePlugin, loaded: list[str]) -> None:
        self.name = plugin.manifest.id
        self._plugin = plugin
        self._loaded = loaded

    def load(self):
        self._loaded.append(self.name)
        return lambda: self._plugin


class FakeEntryPoints(tuple):
    def select(self, *, group: str):
        assert group == "vidsnap.plugins"
        return self


def test_registry_rejects_duplicate_missing_and_cyclic_plugins() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("a", provides=("cap.a",), requires=("cap.b",)))
    registry.register(FakePlugin("b", provides=("cap.b",), requires=("cap.a",)))
    with pytest.raises(ValueError, match="dependency cycle"):
        registry.resolve()


def test_discovery_loads_only_explicit_allowed_ids(monkeypatch) -> None:
    loaded: list[str] = []
    allowed = FakePlugin("vidsnap.tool.sample_evidence")
    denied = FakePlugin("vidsnap.tool.open_url")
    entries = FakeEntryPoints((FakeEntryPoint(allowed, loaded), FakeEntryPoint(denied, loaded)))
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: entries)
    discover_allowed_plugins({"vidsnap.tool.sample_evidence"})
    assert loaded == ["vidsnap.tool.sample_evidence"]
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/plugins/test_registry.py -q`

Expected: FAIL because `vidsnap.plugins` does not exist。

- [ ] **Step 3: 实现插件协议**

```python
class PluginManifest(StrictModel):
    api_version: Literal["vidsnap.plugin/v1"] = "vidsnap.plugin/v1"
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    kind: Literal["tool", "policy", "task", "observer"]
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    model_visible: bool = False


class ToolPlugin(Protocol):
    manifest: PluginManifest
    name: str
    input_model: type[StrictModel]
    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult: ...


class EvidenceSink(Protocol):
    def next_id(self, prefix: Literal["frame", "transcript"]) -> str: ...
    def add(self, evidence: Evidence) -> str: ...


@dataclass(frozen=True, slots=True)
class TranscriptionResponse:
    text: str
    usage: ProviderUsage = field(default_factory=lambda: ProviderUsage(reported=False))


class TranscriptionPort(Protocol):
    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> TranscriptionResponse: ...


class ToolResult(StrictModel):
    status: Literal["completed", "skipped", "failed"]
    evidence_ids: tuple[str, ...] = ()
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    usage: ProviderUsage = Field(default_factory=lambda: ProviderUsage(reported=False))


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    source_path: Path
    probe: MediaProbe
    artifact_root: Path
    media: FFmpegPort
    recognizer: TranscriptionPort | None
    sampler: AdaptiveSampler
    evidence_sink: EvidenceSink
```

`ToolExecutionContext` exposes only source path, probe, artifact root, media port, recognizer, sampler and an `EvidenceSink`; it does not contain credentials, provider URL/client, registry or EventSink.

`SpeechRecognizerAdapter` wraps the existing public `SpeechRecognizer` without changing its signature and returns `reported=False`; the benchmark-specific adapter wraps `FormalModelPort.transcribe_audio` and preserves its real bytes/tokens as `ProviderUsage`. `PluginRegistry` rejects duplicate manifest IDs and duplicate model-visible tool names, and resolves a tool call by `ToolPlugin.name`, never by an arbitrary import path.

- [ ] **Step 4: 实现确定性依赖解析和 allow-list 发现**

`PluginRegistry.resolve()` returns plugins in topological order, sorted by plugin ID within each ready layer. `discover_allowed_plugins(allowed_ids)` calls entry points only when `entry_point.name in allowed_ids`, then verifies the loaded manifest ID matches the entry-point name.

- [ ] **Step 5: 将 SkillRegistry 改成兼容 facade**

Keep `SkillRegistry.names()` and duplicate/allow-list behavior for one release, but implement storage through `PluginRegistry`; `register_builtin_skills` remains callable for existing tests and is marked deprecated in its docstring without emitting runtime warnings.

- [ ] **Step 6: 运行插件与旧 skill 回归**

Run: `.venv/bin/python -m pytest tests/plugins/test_registry.py tests/skills/test_builtin_skills.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add src/vidsnap/plugins src/vidsnap/skills tests/plugins tests/skills
git commit -m "feat: add allow-listed plugin registry"
```

---

### Task 4: 两个默认 Tool Plugin

**Files:**
- Create: `src/vidsnap/plugins/builtin/__init__.py`
- Create: `src/vidsnap/plugins/builtin/transcribe_audio.py`
- Create: `src/vidsnap/plugins/builtin/sample_evidence.py`
- Create: `tests/plugins/test_builtin_tools.py`
- Modify: `src/vidsnap/video/ports.py`
- Modify: `src/vidsnap/video/probe.py`
- Modify: `tests/video/test_probe.py`

**Interfaces:**
- Consumes: `ToolPlugin`, `ToolExecutionContext`, `ToolResult`。
- Produces: `TimeWindow`, `TranscribeAudioArgs`, `SampleEvidenceArgs`, `TranscribeAudioPlugin`, `SampleEvidencePlugin`, `default_tool_plugins()`。

- [ ] **Step 1: 写工具参数与差异轨迹所需行为的失败测试**

```python
class RecordingEvidenceSink:
    def __init__(self) -> None:
        self.items: list[Evidence] = []
        self.counts = {"frame": 0, "transcript": 0}

    def next_id(self, prefix: Literal["frame", "transcript"]) -> str:
        self.counts[prefix] += 1
        return f"{prefix}-{self.counts[prefix]:03d}"

    def add(self, evidence: Evidence) -> str:
        self.items.append(evidence)
        return evidence.id


class FakeWindowMedia:
    def __init__(self) -> None:
        self.sampled_timestamps: list[float] = []

    async def visual_candidates(self, source, probe):
        del source, probe
        return [
            FrameCandidate(timestamp=value, score=1, perceptual_hash=str(value))
            for value in (1.0, 4.0, 6.0, 9.0)
        ]

    async def extract_frames(self, source, candidates, output_dir):
        del source
        output_dir.mkdir(parents=True)
        self.sampled_timestamps = [item.timestamp for item in candidates]
        frames = []
        for index, item in enumerate(candidates):
            path = output_dir / f"{index}.jpg"
            path.write_bytes(b"frame")
            frames.append(ExtractedFrame(path=path, timestamp=item.timestamp, perceptual_hash=item.perceptual_hash))
        return frames


def test_tool_arguments_reject_out_of_bounds_windows() -> None:
    with pytest.raises(ValidationError):
        TranscribeAudioArgs(windows=[{"start_seconds": 8, "end_seconds": 2}])
    with pytest.raises(ValidationError):
        SampleEvidenceArgs(max_frames=97)


@pytest.mark.asyncio
async def test_visual_tool_samples_only_requested_window(tmp_path) -> None:
    media = FakeWindowMedia()
    context = ToolExecutionContext(
        source_path=tmp_path / "video.mp4",
        probe=MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=False),
        artifact_root=tmp_path / "artifacts",
        media=media,
        recognizer=None,
        sampler=AdaptiveSampler(),
        evidence_sink=RecordingEvidenceSink(),
    )
    result = await SampleEvidencePlugin().execute(
        SampleEvidenceArgs(windows=(TimeWindow(start_seconds=4, end_seconds=6),), max_frames=2),
        context,
    )
    assert result.evidence_ids == ("frame-001", "frame-002")
    assert media.sampled_timestamps == [4.0, 6.0]
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/plugins/test_builtin_tools.py -q`

Expected: FAIL because built-in plugin modules do not exist。

- [ ] **Step 3: 扩展 FFmpeg 音频端口的兼容签名**

Implement the exact bounded tool inputs before changing media execution:

```python
class TimeWindow(StrictModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> TimeWindow:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class TranscribeAudioArgs(StrictModel):
    windows: tuple[TimeWindow, ...] = Field(default=(), max_length=3)


class SampleEvidenceArgs(StrictModel):
    windows: tuple[TimeWindow, ...] = Field(default=(), max_length=3)
    max_frames: int = Field(default=12, ge=1, le=96)
```

The kernel performs probe-relative upper-bound validation and remaining-budget validation before plugin execution. Empty windows mean the full locally available range, never an arbitrary source.

Change `extract_audio` to:

```python
async def extract_audio(
    self,
    source: Path,
    output_path: Path,
    *,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> Path: ...
```

The old two-positional-argument call remains valid. Build FFmpeg `-ss` and `-to` arguments only when the optional bounds are present.

- [ ] **Step 4: 实现 ASR 插件**

Validate at most three windows against `context.probe.duration_seconds`. If the probe has no audio, return `skipped` without calling a recognizer. For each valid window, extract one local WAV, call `context.recognizer.transcribe`, allocate `transcript-001`, `transcript-002`, … through `EvidenceSink.next_id`, create one transcript `Evidence`, and add it through `context.evidence_sink.add(...)`. Aggregate real provider usage from every transcription response. Return only evidence IDs, count, status, character count and structured usage in `ToolResult`; never copy transcript text into the event summary.

- [ ] **Step 5: 实现视觉插件**

Filter visual candidates to zero-to-three requested windows, clamp `max_frames` to the remaining kernel frame budget before execution, call `AdaptiveSampler.select(...)`, and extract frames beneath `context.artifact_root`. Allocate `frame-001`, `frame-002`, … through `EvidenceSink.next_id`, create timestamped frame Evidence, and return IDs/count/status. Do not accept paths, URLs, encoding or sampling implementation in the input model.

- [ ] **Step 6: 运行工具和视频回归**

Run: `.venv/bin/python -m pytest tests/plugins/test_builtin_tools.py tests/video/test_probe.py tests/video/test_sampling.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add src/vidsnap/plugins/builtin src/vidsnap/video tests/plugins tests/video
git commit -m "feat: package bounded video tools as plugins"
```

---

### Task 5: 标准 Agent 模型端口与 Qwen JSON 决策

**Files:**
- Modify: `src/vidsnap/providers/base.py:21-55`
- Modify: `src/vidsnap/providers/qwen.py:20-220`
- Modify: `tests/providers/test_qwen.py`

**Interfaces:**
- Consumes: `AgentDecision`, `ProviderUsage`, Evidence、probe、tool JSON schemas。
- Produces: `AgentStepRequest`, `AgentDecisionResponse`, `AgentModelPort.decide_next(...)`, `QwenCompatibleClient.decide_next(...)`。

- [ ] **Step 1: 写 Qwen 决策 wire contract 失败测试**

```python
@pytest.mark.asyncio
async def test_qwen_decision_uses_fixed_model_and_exact_tool_schemas() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        decision = {"kind": "tool_calls", "calls": [{"name": "sample_evidence", "arguments": {"max_frames": 4}}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(decision)}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}})

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    request = AgentStepRequest(
        goal=VideoGoal(objective="What happens?"),
        probe=MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=False),
        evidence=(),
        tool_results=(),
        tool_schemas=(
            {"name": "transcribe_audio", "input_schema": {"type": "object"}},
            {"name": "sample_evidence", "input_schema": {"type": "object"}},
        ),
        output_schema=VideoAnalysisResult.model_json_schema(),
        remaining_model_calls=12,
        remaining_tool_calls=6,
        remaining_frames=96,
    )
    response = await client.decide_next(request)
    assert captured["model"] == "qwen3.8-max"
    planner_input = json.loads(captured["messages"][1]["content"])
    assert {schema["name"] for schema in planner_input["tool_schemas"]} == {"transcribe_audio", "sample_evidence"}
    assert response.decision.calls[0].name == "sample_evidence"


def test_missing_provider_usage_is_not_reported_as_measured_zero() -> None:
    decision = {"kind": "final", "output": {"summary": "x", "claims": [], "required_sections": {}}}
    payload = {"choices": [{"message": {"content": json.dumps(decision)}}]}
    response = QwenCompatibleClient._parse_agent_decision(payload, input_bytes=11)
    assert response.usage.reported is False
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/providers/test_qwen.py -q`

Expected: FAIL because `decide_next` and `AgentStepRequest` do not exist。

- [ ] **Step 3: 实现 provider-neutral 请求/响应类型**

```python
@dataclass(frozen=True, slots=True)
class AgentStepRequest:
    goal: VideoGoal
    probe: MediaProbe
    evidence: tuple[Evidence, ...]
    tool_results: tuple[dict[str, JsonValue], ...]
    tool_schemas: tuple[dict[str, JsonValue], ...]
    output_schema: dict[str, JsonValue]
    remaining_model_calls: int
    remaining_tool_calls: int
    remaining_frames: int
    verifier_feedback: dict[str, JsonValue] | None = None
    format_repair: bool = False


@dataclass(frozen=True, slots=True)
class AgentDecisionResponse:
    decision: AgentDecision
    usage: ProviderUsage


class AgentModelPort(Protocol):
    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse: ...
```

- [ ] **Step 4: 实现 Qwen strict JSON envelope**

`decide_next` sends the fixed model, typed goal/probe/evidence summaries, prior redacted tool-result summaries, remaining budgets and exactly the supplied tool/output schemas. Parse only `AgentDecision`; reject markdown fences, extra keys and natural-language tool instructions with `ProviderError`. Reuse `_image_part` for bounded local frame evidence. Preserve `analyze_evidence` and `plan_tools` until compatibility cleanup.

Add `usage_reported: bool = False` to the existing `ModelResponse` and `ToolPlanResponse` dataclasses without changing positional parameters. Qwen adapters set it to `True` only when the provider actually returned usage; map absence to `ProviderUsage(reported=False)` instead of treating default zero counters as measured zeros.

- [ ] **Step 5: 运行 provider 回归**

Run: `.venv/bin/python -m pytest tests/providers/test_qwen.py tests/providers/test_asr.py tests/providers/test_config.py -q`

Expected: PASS, including fixed-model and no-key blocking tests。

- [ ] **Step 6: 提交**

```bash
git add src/vidsnap/providers tests/providers
git commit -m "feat: add qwen agent decision port"
```

---

### Task 6: 通用视频任务适配器

**Files:**
- Create: `src/vidsnap/tasks/__init__.py`
- Create: `src/vidsnap/tasks/base.py`
- Create: `src/vidsnap/tasks/video_analysis.py`
- Create: `tests/tasks/test_video_analysis.py`

**Interfaces:**
- Consumes: `VideoGoal`, `VideoAnalysisResult`, Evidence、MediaProbe、`ProviderUsage`、现有 `VideoModelPort` 与 `verify_claims`。
- Produces: `TaskAdapter[OutputT, ModelT]`, `TaskVerification`, `VideoAnalysisTaskAdapter`。

- [ ] **Step 1: 写输出解析和 verifier 失败测试**

```python
def test_video_task_adapter_parses_strict_output_and_reuses_verifier() -> None:
    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    payload = {
        "summary": "A person moves.",
        "claims": [{"text": "A person moves.", "evidence": [{"evidence_id": "frame-001"}]}],
        "required_sections": {},
    }
    output = adapter.parse_final(payload)
    evidence = [Evidence(id="frame-001", start_seconds=1, end_seconds=1, modality="frame")]
    media_probe = MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=False)
    verification = adapter.verify(output, evidence=evidence, probe=media_probe)
    assert verification.passed is True


def test_video_task_adapter_rejects_unknown_output_fields() -> None:
    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    payload = {"summary": "No claims.", "claims": [], "required_sections": {}}
    with pytest.raises(ValidationError):
        adapter.parse_final({**payload, "raw_reasoning": "hidden"})


@pytest.mark.asyncio
async def test_video_task_adapter_maps_final_model_usage() -> None:
    class FakeVideoModel:
        async def analyze_evidence(self, evidence, goal):
            del evidence, goal
            return ModelResponse(result=VideoAnalysisResult(summary="Done.", claims=[]), input_tokens=9, output_tokens=2)

    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    output, usage = await adapter.request_final(
        FakeVideoModel(),
        evidence=(),
        probe=MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=False),
    )
    assert output.summary == "Done."
    assert usage.input_tokens == 9
    assert usage.output_tokens == 2
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/tasks/test_video_analysis.py -q`

Expected: FAIL because `vidsnap.tasks` does not exist。

- [ ] **Step 3: 实现 TaskAdapter 协议**

```python
OutputT = TypeVar("OutputT", bound=StrictModel)
ModelT = TypeVar("ModelT", contravariant=True)


class TaskVerification(StrictModel):
    passed: bool
    gates: dict[str, bool]
    targeted_windows: tuple[tuple[float, float], ...] = ()


class TaskAdapter(Protocol, Generic[OutputT, ModelT]):
    goal: VideoGoal
    output_model: type[OutputT]
    async def request_final(
        self,
        model: ModelT,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> tuple[OutputT, ProviderUsage]: ...
    def parse_final(self, payload: dict[str, JsonValue]) -> OutputT: ...
    def verify(self, output: OutputT, evidence: Sequence[Evidence], probe: MediaProbe) -> TaskVerification: ...
```

`VideoAnalysisTaskAdapter.request_final` calls the existing `VideoModelPort.analyze_evidence`, returns its `VideoAnalysisResult`, and maps reported token counters to `ProviderUsage`. `verify` delegates to existing deterministic `verify_claims`.

- [ ] **Step 4: 运行任务适配器与 verifier 回归**

Run: `.venv/bin/python -m pytest tests/tasks/test_video_analysis.py tests/loop/test_verifier.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/vidsnap/tasks tests/tasks
git commit -m "feat: add video task adapter contract"
```

---

### Task 7: HarnessKernel 与 FixedPolicy 兼容迁移

**Files:**
- Create: `src/vidsnap/runtime/__init__.py`
- Create: `src/vidsnap/runtime/context.py`
- Create: `src/vidsnap/runtime/kernel.py`
- Create: `src/vidsnap/runtime/policies.py`
- Create: `tests/runtime/fakes.py`
- Create: `tests/runtime/test_fixed_policy.py`
- Modify: `src/vidsnap/loop/state_machine.py`
- Modify: `src/vidsnap/harness.py:41-410`
- Modify: `tests/test_harness.py`

**Interfaces:**
- Consumes: registry、built-in tools、TaskAdapter、TraceRecorder、provider/model/media ports。
- Produces: `RunContext`, `KernelRunResult`, `HarnessKernel.run(...)`, `ExecutionPolicy`, `FixedPolicy`。

- [ ] **Step 1: 写 Fixed 兼容失败测试**

```python
class FakeMediaPort:
    def __init__(self, *, has_audio: bool) -> None:
        self.has_audio = has_audio

    async def probe(self, source: Path) -> MediaProbe:
        del source
        return MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=self.has_audio)

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source, probe
        return [FrameCandidate(timestamp=1, score=1, perceptual_hash="one")]

    async def extract_frames(self, source, candidates, output_dir):
        del source
        output_dir.mkdir(parents=True)
        path = output_dir / "0.jpg"
        path.write_bytes(b"frame")
        return [ExtractedFrame(path=path, timestamp=candidates[0].timestamp, perceptual_hash="one")]

    async def extract_audio(self, source, output_path, *, start_seconds=0.0, end_seconds=None):
        del source, start_seconds, end_seconds
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return output_path


class FakeRecognizer:
    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        assert audio_bytes == b"audio"
        assert mime_type == "audio/wav"
        return "spoken words"


class FakeRuntimeModel:
    def __init__(self, *, fail_if_decide: bool = False) -> None:
        self.fail_if_decide = fail_if_decide
        self.decide_calls = 0

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        del request
        self.decide_calls += 1
        if self.fail_if_decide:
            raise AssertionError("FixedPolicy must not call decide_next")
        raise AssertionError("No scripted decision configured")

    async def analyze_evidence(self, evidence, goal) -> ModelResponse:
        del goal
        return ModelResponse(
            result=VideoAnalysisResult(
                summary="Grounded.",
                claims=[Claim(text="Grounded.", evidence=[EvidenceReference(evidence_id=evidence[0].id)])],
            )
        )


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def completed_phases(events: list[dict[str, object]]) -> list[str]:
    return [str(event["phase"]) for event in events if event.get("status") in {"completed", "skipped"}]


@pytest.mark.asyncio
async def test_fixed_policy_keeps_order_and_never_calls_agent_decider(tmp_path) -> None:
    model = FakeRuntimeModel(fail_if_decide=True)
    harness = VideoHarness(
        media=FakeMediaPort(has_audio=True),
        model=model,
        recognizer=FakeRecognizer(),
    )
    result = await harness.run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )
    events = read_events(result.run_path)
    assert completed_phases(events) == ["probe_media", "transcribe_audio", "sample_evidence", "synthesize_result", "verify_claims", "terminal"]
    assert model.decide_calls == 0
    assert result.terminal_state is TerminalState.SUCCEEDED
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/runtime/test_fixed_policy.py -q`

Expected: FAIL because runtime package does not exist。

- [ ] **Step 3: 实现 RunContext 与不可绕过 primitive**

`RunContext` owns source, probe, evidence, per-modality Evidence ID counters, budgets, tool-call fingerprints, redacted tool-result summaries, verifier feedback, `task_adapter`, `task_model`, optional `agent_model`, and output. It implements `EvidenceSink.next_id/add` and writes every added item through `RunBundle.write_evidence` before emitting `evidence.added`. `HarnessKernel` exposes only `probe()`, `execute_tool()`, `prepare_direct_baseline()`, `request_fixed_final()`, `request_agent_decision()`, `accept_agent_final()`, `verify()`, and `terminate()` to policies. `prepare_direct_baseline()` is disabled unless the operator selected the benchmark-only Direct policy and always uses the registered local `fps=2` path; it is never included in the model tool table. `request_fixed_final()` delegates to `task_adapter.request_final(task_model, ...)`; `request_agent_decision()` uses only `agent_model`. Each primitive checks active state and budget, emits paired events, and updates context before returning. Normal `VideoHarness` wraps its existing `SpeechRecognizer` in `SpeechRecognizerAdapter`, preserving the public constructor contract.

Keep the public `max_iterations <= 3` contract and its existing meaning: initial acquisition plus bounded verifier-repair cycles. Agent decision turns are counted by `max_model_calls`, and model-visible tools by `max_tool_calls`; do not incorrectly stop Agentic after three model decisions. Replace the old rigid `LoopState` traversal behind the facade, but keep exported terminal states and compatibility event phases.

- [ ] **Step 4: 实现 FixedPolicy**

```python
class FixedPolicy:
    async def run(self, kernel: HarnessKernel, context: RunContext) -> None:
        await kernel.probe(context)
        if context.probe.has_audio:
            await kernel.execute_tool(context, ToolCallRequest(name="transcribe_audio"))
        await kernel.execute_tool(context, ToolCallRequest(name="sample_evidence"))
        await kernel.request_fixed_final(context)
        await kernel.verify(context)
```

Implement bounded targeted repair by rerunning `sample_evidence` only for verifier-provided windows, then final+verify, at most the existing two repair rounds.

- [ ] **Step 5: 将 VideoHarness 改为装配器**

Keep constructor arguments and `run(...)` signature. Build the default plugin registry, `VideoAnalysisTaskAdapter`, `HarnessKernel`, and choose `FixedPolicy` when `tool_mode == "fixed"`. Keep `HarnessRunResult` fields unchanged.

- [ ] **Step 6: 运行 Fixed 与公共接口回归**

Run: `.venv/bin/python -m pytest tests/runtime/test_fixed_policy.py tests/test_harness.py tests/api/test_app.py tests/test_cli.py -q`

Expected: PASS; existing test confirms default Fixed does not request an agent plan。

- [ ] **Step 7: 提交**

```bash
git add src/vidsnap/runtime src/vidsnap/harness.py src/vidsnap/loop/state_machine.py tests/runtime tests/test_harness.py
git commit -m "refactor: route fixed harness through plugin kernel"
```

---

### Task 8: 真正的多轮 AgenticPolicy

**Files:**
- Create: `tests/runtime/test_agentic_policy.py`
- Create: `tests/runtime/test_policy_security.py`
- Modify: `src/vidsnap/runtime/policies.py`
- Modify: `src/vidsnap/runtime/kernel.py`
- Modify: `src/vidsnap/runtime/context.py`
- Modify: `src/vidsnap/harness.py`
- Modify: `tests/runtime/fakes.py`
- Modify: `tests/test_harness.py`

**Interfaces:**
- Consumes: `AgentModelPort.decide_next`, `AgentDecision`, registry tool schemas, kernel primitives。
- Produces: `AgenticPolicy` with evidence feedback, one per-run format repair and real variable traces。

- [ ] **Step 1: 写四种不同轨迹的失败测试**

```python
def tool_decision(name: str, **arguments: JsonValue) -> AgentDecision:
    return AgentDecision(
        kind="tool_calls",
        calls=(ToolCallRequest(name=name, arguments=dict(arguments)),),
    )


def final_decision(evidence_id: str) -> AgentDecision:
    return AgentDecision(
        kind="final",
        output={
            "summary": "Grounded.",
            "claims": [{"text": "Grounded.", "evidence": [{"evidence_id": evidence_id}]}],
            "required_sections": {},
        },
    )


class ScriptedAgentModel(FakeRuntimeModel):
    def __init__(self, decisions: list[AgentDecision]) -> None:
        super().__init__()
        self.decisions = deque(decisions)
        self.requests: list[AgentStepRequest] = []

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        self.requests.append(request)
        self.decide_calls += 1
        return AgentDecisionResponse(decision=self.decisions.popleft(), usage=ProviderUsage())


async def run_scripted_agent(decisions: list[AgentDecision], tmp_path: Path):
    model = ScriptedAgentModel(decisions)
    harness = VideoHarness(media=FakeMediaPort(has_audio=True), model=model, recognizer=FakeRecognizer())
    result = await harness.run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Answer from evidence"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "run"),
    )
    return result, model


def completed_tool_names(events: list[dict[str, object]]) -> list[str]:
    return [
        str(event["payload"]["name"])
        for event in events
        if event.get("event_type") == "tool.call.completed"
    ]


@pytest.mark.parametrize(
    ("decisions", "expected_tools"),
    [
        ([tool_decision("transcribe_audio"), final_decision("transcript-001")], ["transcribe_audio"]),
        ([tool_decision("sample_evidence", max_frames=1), final_decision("frame-001")], ["sample_evidence"]),
        ([tool_decision("sample_evidence", max_frames=1), tool_decision("transcribe_audio"), final_decision("frame-001")], ["sample_evidence", "transcribe_audio"]),
        ([tool_decision("sample_evidence", windows=[{"start_seconds": 0, "end_seconds": 5}], max_frames=1), tool_decision("sample_evidence", windows=[{"start_seconds": 7, "end_seconds": 9}], max_frames=1), final_decision("frame-001")], ["sample_evidence", "sample_evidence"]),
    ],
)
@pytest.mark.asyncio
async def test_agentic_policy_emits_real_variable_tool_traces(decisions, expected_tools, tmp_path) -> None:
    result, model = await run_scripted_agent(decisions, tmp_path)
    assert completed_tool_names(read_events(result.run_path)) == expected_tools
    assert model.requests[-1].evidence
```

- [ ] **Step 2: 写越权与预算失败测试**

```python
@pytest.mark.asyncio
async def test_agentic_policy_never_executes_unknown_or_repeated_paid_calls(tmp_path) -> None:
    result, _ = await run_scripted_agent([tool_decision("open_url", url="https://example.com")], tmp_path)
    assert result.terminal_state is TerminalState.FAILED
    assert completed_tool_names(read_events(result.run_path)) == []


@pytest.mark.asyncio
async def test_agentic_policy_rejects_duplicate_paid_call(tmp_path) -> None:
    repeated = tool_decision("sample_evidence", max_frames=1)
    result, _ = await run_scripted_agent([repeated, repeated], tmp_path)
    assert result.terminal_state is TerminalState.FAILED
    assert completed_tool_names(read_events(result.run_path)) == ["sample_evidence"]


@pytest.mark.asyncio
async def test_agentic_policy_exhausts_at_six_tool_calls(tmp_path) -> None:
    decisions = [
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": index, "end_seconds": index + 0.5}],
            max_frames=1,
        )
        for index in range(7)
    ]
    result, _ = await run_scripted_agent(decisions, tmp_path)
    assert result.terminal_state is TerminalState.EXHAUSTED
```

- [ ] **Step 3: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/runtime/test_agentic_policy.py tests/runtime/test_policy_security.py -q`

Expected: FAIL because Agentic still uses one-shot ToolPlan or is not implemented。

- [ ] **Step 4: 实现多轮循环**

```python
class AgenticPolicy:
    async def run(self, kernel: HarnessKernel, context: RunContext) -> None:
        await kernel.probe(context)
        while context.terminal_state is None:
            decision = await kernel.request_agent_decision(context)
            if decision.kind == "tool_calls":
                for call in decision.calls:
                    await kernel.execute_tool(context, call)
                continue
            await kernel.accept_agent_final(context, decision.output)
            await kernel.verify(context)
```

After every tool result, the next `AgentStepRequest.evidence` and tool-result summaries must include newly added Evidence IDs. Verifier feedback is passed only as structured gate names and targeted windows.

`verify()` terminates only when verification passes or no repair round remains. When a final answer fails verification and repair remains, it records `repair.requested`, clears the rejected output, stores only failed gate names/targeted windows, and leaves the context active so the next loop iteration asks the model what to do. The model still cannot choose the verifier or terminal state.

- [ ] **Step 5: 实现一次格式修复和调用指纹**

Catch the first malformed decision, set `context.format_repair_used = True`, emit `agent.decision` failed, and make one request with `format_repair=True`. A second malformed decision terminates `FAILED`. Fingerprint `name + canonical arguments`; reject duplicate paid calls before execution.

- [ ] **Step 6: 运行 Agentic、Fixed 和安全回归**

Run: `.venv/bin/python -m pytest tests/runtime tests/test_harness.py tests/providers/test_qwen.py -q`

Expected: PASS, with four distinct event sequences and unchanged Fixed sequence。

- [ ] **Step 7: 提交**

```bash
git add src/vidsnap/runtime src/vidsnap/harness.py tests/runtime tests/test_harness.py
git commit -m "feat: add iterative agentic tool loop"
```

---

### Task 9: Direct/Fixed/Agentic benchmark 统一到 Kernel

**Files:**
- Create: `src/vidsnap/benchmark/adapters.py`
- Modify: `src/vidsnap/benchmark/live.py:459-790`
- Modify: `scripts/run_agentic_benchmark.py:280-360`
- Modify: `tests/benchmark/test_live.py`
- Modify: `tests/test_agentic_benchmark_script.py`
- Preserve: `src/vidsnap/benchmark/reporting.py`

**Interfaces:**
- Consumes: HarnessKernel、DirectPolicy、FixedPolicy、AgenticPolicy、现有 `FormalCase` 与 QwenFormalClient。
- Produces: `MCQTaskAdapter`, `BenchmarkRunProjector.to_outcome(...)`; unchanged `VariantOutcome` and report schema。

- [ ] **Step 1: 写统一内核与逐 variant RunBundle 失败测试**

```python
async def run_three_variants(tmp_path: Path) -> list[VariantOutcome]:
    case = make_case(tmp_path)
    engine = FormalBenchmarkEngine(media=FakeFormalMedia(), model=FakeFormalModel())
    outcomes = []
    for variant in ("direct", "fixed", "agentic"):
        outcomes.append(
            await engine.run_case(
                case,
                variant=variant,
                work_dir=tmp_path / variant,
                direct_input_mode="frames_2fps",
            )
        )
    return outcomes


@pytest.mark.asyncio
async def test_all_benchmark_variants_emit_kernel_runbundles(tmp_path) -> None:
    outcomes = await run_three_variants(tmp_path)
    for variant in ("direct", "fixed", "agentic"):
        events = read_events(tmp_path / variant / "run")
        assert events[0]["event_type"] == "run.started"
        assert events[-1]["event_type"] == "run.completed"
    assert {item.variant for item in outcomes} == {"direct", "fixed", "agentic"}
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/benchmark/test_live.py::test_all_benchmark_variants_emit_kernel_runbundles -q`

Expected: FAIL because `FormalBenchmarkEngine` bypasses HarnessKernel and writes no trace ledger。

- [ ] **Step 3: 实现 MCQTaskAdapter 和 outcome projector**

`MCQTaskAdapter.request_final` calls `FormalModelPort.answer_mcq` with the Evidence-derived frames/transcript or Direct frame sequence and maps `MCQModelResponse` counters to `ProviderUsage`. `parse_final` accepts only `{"answer": "A"}` where the answer is one declared option label; the adapter wraps existing plain-text responses as that dictionary only after `parse_mcq_answer` succeeds. `verify` reproduces the five existing deterministic gates. `BenchmarkRunProjector` derives answer, correctness, selected tool names, Direct input mode, provider usage totals, latency and verifier result from `KernelRunResult` plus events.

Add `usage_reported: bool = False` to `MCQModelResponse`. `FormalTranscriptionAdapter` converts `FormalModelPort.transcribe_audio` into the plugin `TranscriptionPort`, preserving one model call and the returned bytes/tokens in `ToolResult.usage`. This adapter is mandatory for benchmark Fixed/Agentic so ASR cost is not lost; ordinary SDK Fixed continues to use the compatibility recognizer adapter.

Add `QwenFormalClient.decide_next(AgentStepRequest) -> AgentDecisionResponse`. It uses the same fixed `qwen3.8-max`, emits either bounded tool calls or a final `{"answer": "<declared label>"}` output, and replaces `plan_tools` only for the new Agentic runtime. Its request includes the MCQ output schema and declared option labels. Keep `plan_tools` as a compatibility method until the final conformance task.

- [ ] **Step 4: 实现 DirectPolicy 的 fps=2 path**

Direct calls `kernel.prepare_direct_baseline(context)`, which deterministically invokes `extract_timeline_frames(..., fps=2)`, records the complete resulting frame sequence as baseline input, performs one final MCQ model call, and verifies. It never exposes the extraction operation in the model tool table. Preserve the existing registered protocol where Direct can exceed the 96 model-selected-evidence cap (the short smoke already reaches about 147 frames); count every frame in usage and do not truncate it silently. The primitive marks those items `budget_class="direct_baseline"`, while every Tool Plugin frame remains `budget_class="model_selected"` and consumes the 96-frame cap.

- [ ] **Step 5: 替换 FormalBenchmarkEngine 的平行流程**

Keep `run_case(case, variant, work_dir, direct_input_mode)` public signature. Assemble the correct policy and MCQ adapter, run the common kernel into `work_dir / "run"`, then project to the existing `VariantOutcome`. Remove `_selected_tools`, `_transcript`, `_adaptive_frames`, `_verify`, `_outcome`, and `_failure_outcome` only after the new focused tests pass.

- [ ] **Step 6: 保持 smoke/formal 报告规则不变**

Run: `.venv/bin/python -m pytest tests/benchmark/test_live.py tests/benchmark/test_reporting.py tests/test_agentic_benchmark_script.py -q`

Expected: PASS; smoke report still omits all superiority/noninferiority fields and retains `frames_2fps`. Formal reporting still uses the external manifest's pre-registered independent labels for `pre_registered_tool_selection_alignment`; runtime code never derives or rewrites those labels from observed outcomes.

- [ ] **Step 7: 提交**

```bash
git add src/vidsnap/benchmark scripts/run_agentic_benchmark.py tests/benchmark tests/test_agentic_benchmark_script.py
git commit -m "refactor: unify benchmark variants on harness kernel"
```

---

### Task 10: RunBundle 轨迹读取与 truth-only 投影

**Files:**
- Create: `src/vidsnap/trace/__init__.py`
- Create: `src/vidsnap/trace/models.py`
- Create: `src/vidsnap/trace/reader.py`
- Create: `tests/trace/conftest.py`
- Create: `tests/trace/test_reader.py`

**Interfaces:**
- Consumes: `manifest.json`, `events.jsonl`, optional benchmark `outcomes.jsonl`。
- Produces: `TraceDocument`, `TraceLane`, `TraceItem`, `read_trace(path)`。

- [ ] **Step 1: 写新旧 trace 失败测试**

```python
@pytest.fixture
def traced_run(tmp_path: Path) -> Path:
    bundle = RunBundle.create(tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1")
    recorder = TraceRecorder(bundle, clock=iter((0.0, 1.0, 1.25, 1.3, 1.5, 2.0)).__next__)
    run_span = recorder.start("run", phase="run")
    model_span = recorder.start("model.request", phase="agent_decision", turn=1, step=1)
    recorder.finish(model_span, status="completed", usage=ProviderUsage(input_tokens=7, output_tokens=3))
    tool_span = recorder.start("tool.call", phase="sample_evidence", turn=1, step=2, payload={"name": "sample_evidence"})
    recorder.finish(tool_span, status="completed", payload={"name": "sample_evidence"})
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)
    return bundle.path


@pytest.fixture
def legacy_smoke_dir(tmp_path: Path) -> Path:
    path = tmp_path / "legacy"
    path.mkdir()
    (path / "report.json").write_text(json.dumps({"status": "SMOKE_SUCCEEDED", "case_count": 6}))
    (path / "outcomes.jsonl").write_text(json.dumps({"case_id": "c1", "variant": "agentic", "usage": {"model_calls": 2}}) + "\n")
    return path


def test_reader_projects_only_recorded_events(traced_run) -> None:
    trace = read_trace(traced_run)
    assert [item.event_type for item in trace.items] == [
        "run.started",
        "model.request.started",
        "model.request.completed",
        "tool.call.started",
        "tool.call.completed",
        "run.completed",
    ]
    assert trace.summary_only is False
    assert trace.duration_ms == 2_000


def test_legacy_outcome_is_summary_only_and_has_no_invented_duration(legacy_smoke_dir) -> None:
    trace = read_trace(legacy_smoke_dir)
    assert trace.summary_only is True
    assert trace.duration_ms is None
    assert all(item.duration_ms is None for item in trace.items)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/trace/test_reader.py -q`

Expected: FAIL because trace package does not exist。

- [ ] **Step 3: 实现严格 reader**

Read JSONL line-by-line with Pydantic validation. Pair spans only by matching `correlation_id` and base event type. Assign lanes exactly: run/probe → `input`, model/agent → `model`, tool/evidence → `tools`, verifier/repair/terminal → `verifier`. Overall duration comes only from a paired `run.started/run.completed` span; if that pair or any child pair is missing, keep its duration `None` and preserve only the recorded status. Provider URL is not part of `TraceDocument`.

- [ ] **Step 4: 实现 legacy summary-only reader**

When `trace_schema` is absent, accept only manifest terminal state and outcome-level usage. Do not synthesize model or tool start/result rows. Set `summary_only=True` and include limitation text `"step-level events were not recorded"`.

- [ ] **Step 5: 运行 trace reader 回归**

Run: `.venv/bin/python -m pytest tests/trace/test_reader.py tests/loop/test_events.py tests/loop/test_run_bundle.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/vidsnap/trace tests/trace
git commit -m "feat: project truthful run traces"
```

---

### Task 11: 自包含轨迹 HTML 与 CLI

**Files:**
- Create: `src/vidsnap/trace/export.py`
- Create: `src/vidsnap/trace/assets/trace.html`
- Create: `tests/trace/test_export.py`
- Modify: `src/vidsnap/cli.py:13-20,53-60`
- Modify: `tests/test_cli.py`
- Modify: `pyproject.toml:30-40`
- Modify: `tests/test_distribution_assets.py`

**Interfaces:**
- Consumes: `TraceDocument`。
- Produces: `export_trace(source: Path, output: Path, include_thumbnails: bool = False) -> Path`, CLI `vidsnap trace export`。

- [ ] **Step 1: 写脱敏、自包含与 CLI 失败测试**

```python
def test_export_is_self_contained_and_contains_no_network_or_secrets(tmp_path, traced_run) -> None:
    output = export_trace(traced_run, tmp_path / "trace.html")
    html = output.read_text()
    assert "tool.call.completed" in html
    assert "https://" not in html
    assert "fetch(" not in html
    assert "WebSocket" not in html
    assert "Authorization" not in html
    assert "data:image" not in html


def test_cli_lists_trace_export() -> None:
    result = runner.invoke(app, ["trace", "--help"])
    assert result.exit_code == 0
    assert "export" in result.stdout
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/trace/test_export.py tests/test_cli.py -q`

Expected: FAIL because exporter and trace command do not exist。

- [ ] **Step 3: 实现安全 HTML 注入**

Load packaged template bytes, serialize `TraceDocument.model_dump(mode="json")`, call `.replace("<", "\\u003c")`, and replace exactly one `__VIDSNAP_TRACE_JSON__` marker. Reject non-empty output paths to avoid accidental overwrite. `include_thumbnails=False` never reads artifacts.

- [ ] **Step 4: 实现轨迹布局**

Template contains: top duration/turn/model-call/tool-call summary; Input/Model/Tools/Verifier lanes; searchable chronological rows; expandable redacted payload/usage; Direct/Fixed/Agentic selector when multiple traces share a case. Use only embedded CSS/JavaScript and the embedded JSON. Display `未记录` for missing duration and a visible `summary-only` limitation for legacy runs.

- [ ] **Step 5: 增加 CLI 与打包资产**

```python
from typing import Annotated


trace_app = typer.Typer(help="Export truthful local run traces.")
app.add_typer(trace_app, name="trace")


@trace_app.command("export")
def trace_export(
    source: Path,
    output: Annotated[Path, typer.Option("--output")],
    include_thumbnails: bool = False,
) -> None:
    typer.echo(str(export_trace(source.resolve(), output.resolve(), include_thumbnails)))
```

Add the template to Hatch `force-include` and distribution-asset tests.

- [ ] **Step 6: 运行 exporter、CLI 与 wheel 资产回归**

Run: `.venv/bin/python -m pytest tests/trace/test_export.py tests/test_cli.py tests/test_distribution_assets.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add src/vidsnap/trace src/vidsnap/cli.py tests/trace tests/test_cli.py tests/test_distribution_assets.py pyproject.toml
git commit -m "feat: export local harness trace viewer"
```

---

### Task 12: Conformance、文档与工具/数据审阅清单

**Files:**
- Create: `docs/default-tools-and-data-review.md`
- Modify: `src/vidsnap/conformance.py`
- Modify: `tests/test_conformance.py`
- Modify: `tests/test_no_saas_dependencies.py`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/migration-to-harness.md`

**Interfaces:**
- Consumes: 默认 plugin registry、LoopSpec、trace template、CLI。
- Produces: 新 conformance checks 与用户后续审阅清单。

- [ ] **Step 1: 写 conformance 失败测试**

```python
def test_conformance_requires_exact_default_model_visible_tools_and_trace_asset() -> None:
    report = run_conformance()
    assert report.checks["default_model_visible_tools"] is True
    assert report.details["default_model_visible_tool_names"] == ["sample_evidence", "transcribe_audio"]
    assert report.checks["trace_template_packaged"] is True
    assert report.checks["plugin_dependency_graph"] is True
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `.venv/bin/python -m pytest tests/test_conformance.py -q`

Expected: FAIL because new conformance fields do not exist。

- [ ] **Step 3: 实现 conformance 检查**

Validate the exact default model-visible tool-name set (report it in canonical sorted order), plugin dependency resolution, `vidsnap.trace/v1`, packaged template, Fixed default policy, model/tool/frame/wall budgets, and absence of SaaS runtime imports. Fixed execution order remains an independent assertion: `transcribe_audio` then `sample_evidence`.

- [ ] **Step 4: 更新公开文档**

Document the plugin trust boundary, true Agentic loop, Fixed compatibility, trace export command, summary-only legacy behavior, and explicit distinction between infrastructure validation and benchmark evidence. Do not add live result claims.

- [ ] **Step 5: 写后续审阅清单而不扩展能力**

`docs/default-tools-and-data-review.md` must contain two frozen sections:

```text
当前默认内置工具：transcribe_audio、sample_evidence。
当前可选数据入口：本地视频、可用本地字幕、外部 benchmark manifest、RunBundle evidence/trace metadata。
```

Then list review questions for default-vs-optional classification, privacy/licensing, cost and whether OCR/scene metadata should become plugins. Mark every proposed addition as `not enabled` so this task does not silently broaden the runtime.

- [ ] **Step 6: 运行完整离线发布门槛**

Run:

```bash
.venv/bin/ruff format --check src tests scripts
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/vidsnap conformance
.venv/bin/python scripts/secret_scan.py
git diff --check
```

Expected: all commands exit 0; pytest reports zero failures; secret scan reports no matches。

- [ ] **Step 7: 验证没有 live 调用或结果文件进入 git**

Run:

```bash
git status --short
git ls-files | rg '(outcomes\.jsonl|report\.json|manifest\.jsonl|RunBundle|\.mp4$|\.wav$)' && exit 1 || true
```

Expected: only intended source/test/doc changes before commit; the second command finds no prohibited result/media files。

- [ ] **Step 8: 提交**

```bash
git add src/vidsnap/conformance.py tests README.md docs
git commit -m "docs: finalize plugin harness conformance"
```

- [ ] **Step 9: 停在用户审阅门槛**

Report implementation verification separately from benchmark evidence, then present `docs/default-tools-and-data-review.md` to the user. Do not enable an additional tool or data source until that review is complete.

---

## Final Review Checklist

- [ ] `VideoHarness.run(...)` and existing CLI/API behavior remain compatible.
- [ ] Fixed performs no Agentic decision call and keeps ASR → visual order.
- [ ] Agentic fixtures produce at least four different real event sequences.
- [ ] Every model/tool start has one matching completed/failed event and correlation ID.
- [ ] Unknown tools, model/URL/prompt/budget fields and duplicate paid calls never execute.
- [ ] Direct/Fixed/Agentic benchmark paths use one Kernel and retain report schema/rules.
- [ ] Legacy smoke is visibly summary-only; no step or duration is fabricated.
- [ ] Static trace HTML is self-contained, offline, redacted and thumbnail-free by default.
- [ ] No live benchmark was run and no credentials/media/results were committed.
- [ ] Full offline release gate passes before claiming implementation completion.
- [ ] Default tools and optional data remain unchanged until the user review.
