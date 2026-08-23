# Plugin-first Video Agent Harness 设计

## 状态与结论

本设计把 VidSnap 从“带少量工具选择的固定视频流水线”演进为一个面向视频任务的插件式 Agent Harness。它借鉴 DeepSeek Harness 最有价值的三点：可组合插件、模型与工具结果之间的多步循环、由真实事件生成的轨迹；不复制通用编码 Agent、账号系统或 SaaS 工作区。

已确认的主方向是：

- Python 内核保持本地优先、无数据库、无账号、无跨请求状态；
- 默认推理模型继续固定为 `qwen3.8-max`；内部 benchmark 包括 ASR 在内的所有模型调用都固定为 `qwen3.8-max`；
- 默认及 benchmark 中，模型可见的采集工具仍只有 `transcribe_audio` 和 `sample_evidence`；
- Fixed 保持默认行为和调用顺序兼容；
- Agentic 改为真正的“模型决定下一步 → 工具执行 → 结果返回模型 → 模型继续或结束”；
- RunBundle 自动记录真实步骤，轨迹查看器只展示已记录事件，不猜测缺失步骤；
- Direct、Fixed、Agentic 最终共用同一运行内核与计量方式。

这份文档只定义架构，不包含 live benchmark 结论，也不授权 54-case formal。

## 为什么要改

当前 Agentic 实现只在开始时让 Qwen 返回一次工具名字列表。程序随后仍按固定顺序执行：探测视频、可选 ASR、可选视觉采样、一次回答、验证。模型看不到工具执行结果，也不能根据新证据再次调用工具或缩小时间范围。

现有 6-case smoke 也暴露了这个结构限制：每个 Agentic outcome 都是固定两次模型调用，工具选择只出现“视觉”与“语音 + 视觉”两种组合，而且 benchmark 只保存最终 outcome，没有逐工具 start/result 事件。因此，旧数据无法支持 DeepSeek Harness 风格的真实轨迹；任何把固定流水线画成逐步 Agent 决策的页面都属于推测，不能作为运行证据。

## 目标与非目标

### 目标

1. 让工具成为可注册、可替换、可单测的独立插件，而不是 `VideoHarness` 内部的绑定方法。
2. 让 Agentic 模式根据每轮已有证据选择下一次工具和受限参数。
3. 让预算、权限、验证和终止权始终掌握在 Harness 内核，而不是交给模型。
4. 让每个模型请求、工具调用、工具结果、验证结果和终止状态自动进入事件账本。
5. 让轨迹查看器成为事件账本的只读投影，能够解释“为什么这一条轨迹不同”。
6. 让 benchmark 复用正式运行内核，避免 benchmark 与 SDK 各自维护一套 Agentic 逻辑。
7. 保持现有 Fixed 用户的 SDK、CLI、HTTP 接口和默认行为兼容。

### 非目标

- 不恢复 React/Vite 产品前端、登录、工作区、任务历史、数据库、Redis、Celery 或计费。
- 不构建通用电脑操作 Agent，不加入 shell、浏览器、任意 URL 或任意网络请求工具。
- 不允许模型安装插件、改变插件白名单、选择模型、端点、prompt、预算或 verifier。
- 不保存隐藏推理、Authorization、API Key、原始 provider 请求或原始 provider 响应。
- 不为旧 smoke 伪造逐步轨迹。
- 本阶段不扩大数据集，也不运行 54-case formal。

## 总体架构

内核只保留六项不可绕过的职责：

1. 装载经过操作者批准的插件集合；
2. 校验插件依赖、名称、版本和工具参数；
3. 驱动 Fixed 或 Agentic 执行策略；
4. 在每一步前后执行权限与预算检查；
5. 将结构化事件追加到 RunBundle；
6. 对最终结果执行确定性 verifier 并给出真实终态。

内核之上分为四类可组合部件：

- **Tool Plugin**：模型可能调用的能力，例如 ASR 和视觉证据采样；
- **Execution Policy**：决定下一步如何产生，首批为 Fixed、Agentic 和 benchmark-only Direct；
- **Task Adapter**：定义任务输入、最终输出 schema 和解析方式，首批为通用视频分析与 MCQ；
- **Observer**：消费事件但不改变执行结果，首批为终端摘要和轨迹导出。

预算守卫、权限校验、事件顺序、RunBundle ledger 和 verifier 属于内核安全边界，不做成可被普通插件卸载的能力。这是对 DeepSeek Harness“插件化”思想的有意收缩：可扩展性不能让模型或第三方工具绕过成本与真实性约束。

## 插件契约

### PluginManifest

每个插件提供一个严格 manifest：

```text
api_version: vidsnap.plugin/v1
id: 稳定且唯一的插件 ID
version: 语义版本
kind: tool | policy | task | observer
provides: 本插件提供的 capability
requires: 启动前必须存在的 capability
model_visible: 是否出现在模型工具表中
```

注册表拒绝重复 ID、缺失依赖、循环依赖、未知 kind，以及同一 capability 的未声明冲突。插件在一个 run 开始前完成装配，运行期间不可增删。

首版支持两种装载方式：

- SDK 显式传入插件实例；
- Python package entry point `vidsnap.plugins` 发现本机已安装插件，但只有同时出现在操作者 allow-list 中的 ID 才会装载。

发现插件不等于授权插件。模型永远看不到安装或装载接口。第三方 Python 插件属于本机受信代码，不被宣传为安全沙箱；内部 benchmark 只装载仓库自带插件。

### ToolPlugin

Tool Plugin 必须声明：

- 稳定名称和版本；
- Pydantic 输入 schema 与结果 schema；
- 所需 capability；
- 是否会产生 Evidence；
- 执行方法 `execute(validated_args, ToolContext) -> ToolResult`。

`ToolContext` 只暴露该工具需要的受限能力，例如媒体读取、EvidenceSink 和 BudgetGuard，不暴露 API Key、provider client、插件注册表或任意文件系统入口。内核为每次调用分配 `call_id`；模型不能自行指定或复用它。

### 首批模型可见工具

`transcribe_audio` 的参数只允许：

- 零到三个视频时间窗；
- 时间窗必须位于 probe 得到的真实时长内；
- 未给时间窗时表示在剩余音频预算内处理全段。

返回值是 transcript Evidence 的 ID、时间范围、字符数和状态。完整 transcript 存在 RunBundle evidence 文件中，不复制到事件 payload。

`sample_evidence` 的参数只允许：

- 零到三个视频时间窗；
- 本次请求的最大帧数，且不能超过剩余帧预算；
- 不允许模型指定文件名、采样实现、远程 URL 或图片编码方式。

返回值是 frame Evidence 的 ID、时间戳、尺寸、字节数和状态。采样策略仍由插件内部确定。

默认 profile 和内部 benchmark 的模型工具表严格等于这两个工具。其他本地插件只有在另一个由操作者明确配置的 profile 中才可能对模型可见。

## 三种执行策略

### FixedPolicy

Fixed 继续是 `HarnessPolicy.tool_mode` 的默认值，不增加 planner 调用。执行顺序保持：

```text
probe → transcribe_audio（有音频时）→ sample_evidence
      → final model call → verifier → bounded repair/terminal
```

底层虽然改用插件和统一事件账本，但现有 `VideoHarness.run(...)`、`HarnessRunResult`、CLI `vidsnap analyze` 和 HTTP `/v1/analyze` 的输入输出保持兼容。

### AgenticPolicy

Agentic 不再生成一次性 `ToolPlan`。每个模型步骤必须返回严格 JSON `AgentDecision`，且只能是以下二选一：

```text
tool_calls:
  calls: 1..2 个已允许工具及其参数

final:
  output: 当前 Task Adapter 要求的结构化答案
```

内核拒绝额外字段、未知工具、无效参数、相同参数的重复付费调用和超预算调用。整次 run 只允许在剩余模型预算内进行一次结构修复；再次出现无效结构即结束为 `FAILED`。

### DirectPolicy

Direct 只用于 benchmark。它把同一视频按注册协议转换为完整 `fps=2` 帧序列，并直接进入最终模型调用。它不把帧采集暴露成模型工具，但仍通过同一 Kernel、Task Adapter、provider usage 计量、verifier 与事件账本执行。

## 真正的 Agent 循环

Agentic 一次运行遵循下面的闭环：

1. Harness 确定性 probe 视频并写入 `probe.completed`。
2. 内核向 Qwen 提供任务、probe 摘要、当前 Evidence 摘要、剩余预算和当前允许的两个工具 schema。
3. Qwen 返回一个 `AgentDecision`。
4. 如果是工具调用，内核先校验权限、参数和预算，再按返回顺序逐个执行。
5. 每个工具结果作为结构化 Evidence 摘要进入下一轮模型上下文；图像 Evidence 以受限 data URI 附在对应 Evidence ID 后。
6. Qwen 可以继续调用工具、换另一个工具、缩小时间窗，或提交最终答案。
7. 最终答案通过 Task Adapter 解析，再由 Harness verifier 检查。
8. verifier 通过则 `SUCCEEDED`；未通过且仍有 repair 与预算时，结构化失败 gate 和建议时间窗进入下一轮；否则按事实结束为 `PARTIAL`、`NO_OP`、`EXHAUSTED`、`BLOCKED` 或 `FAILED`。

模型永远不能直接改变终态。一次运行继续沿用最大 12 次模型调用、96 帧和 900 秒墙钟上限，并新增最多 6 次模型可见工具调用的默认上限。现有 Fixed 运行不会因为新增上限而改变当前调用顺序。

## Provider 边界

内核通过固定的 `QwenModelPlugin` 完成决策与最终回答；推理模型名固定为 `qwen3.8-max`。普通 Fixed 运行的 `transcribe_audio` 继续通过现有 `SpeechRecognizer` port 使用已配置的内置识别器或明确的本地识别插件，以保持兼容。内部 benchmark profile 则明确把 ASR 也绑定到 `qwen3.8-max`，确保实验中的所有模型调用一致。所有 endpoint 与凭据只能由本机环境注入；请求对象、HTTP API 和 Tool Plugin 参数都不能覆盖它们。

Provider adapter 负责把标准 `AgentDecision` 映射到 Qwen 兼容端点。即使端点不支持原生 function calling，也使用同一个严格 JSON envelope，不退化为自然语言工具指令。Provider usage 必须以结构化计数返回；端点缺失 usage 时新增 `reported=false`。为兼容现有聚合，数值字段可保留为 0，但报告必须标记为“未报告”，不能解释成真实零值，也不能自行估算成 provider 实报。

## 事件账本与 RunBundle

每次运行自动产生 append-only 事件。业务插件不能直接写 `events.jsonl`；它们只能通过内核 EventSink 发布经过类型校验的事件。

现有 `RunEvent` 的 `sequence`、`phase`、`payload`、`occurred_at` 字段继续保留，并增加：

- `event_id`：Harness 生成的唯一 ID；
- `event_type`：稳定类型；
- `turn` 与 `step`：模型轮次和该轮内步骤；
- `parent_event_id`：父事件；
- `correlation_id`：配对 request/result 或 start/completed；
- `monotonic_offset_ms`：相对本次运行开始的时间；
- `status`：started、completed、failed、blocked 或 skipped；
- `usage`：允许保存的 calls、frames、bytes、tokens；
- `duration_ms`：仅在真实测得时写入。

首批稳定事件类型：

```text
run.started / run.completed
probe.started / probe.completed
model.request.started / model.request.completed / model.request.failed
agent.decision
tool.call.started / tool.call.completed / tool.call.failed
evidence.added
verifier.completed
budget.updated
repair.requested
```

事件 payload 使用每种事件的字段 allow-list。禁止写入凭据、Authorization、原始 provider body、原始 provider response、完整 transcript、图片 data URI 和隐藏推理。RunBundle evidence 与 artifact 文件继续保存本地证据，manifest 继续记录哈希和脱敏 provider identity。

为兼容现有使用者，RunBundle 暂时继续写 `vidsnap.run/v1`，新增 `trace_schema: vidsnap.trace/v1`；旧字段只做加法扩展。轨迹读取器同时支持旧事件：旧 run 被明确标记为 `summary_only`，缺失步骤和时长保持空白。

## 轨迹查看器

轨迹查看器是一个本地诊断工具，不是 SaaS 前端。它读取一个 RunBundle 或一个外部 benchmark 结果目录，生成可离线打开的静态 HTML；不需要 React、数据库或常驻服务。

页面采用与用户提供的 DeepSeek Harness 参考图相近的信息层级：

- 顶部显示真实 duration、turns、model calls、tool calls；
- 时间轴按 Input / Model / Tools / Verifier 分 lane；
- 下方按事件顺序显示 MODEL、TOOL CALL、TOOL RESULT、VERIFY 和 TERMINAL；
- 每个调用可以展开查看脱敏参数、Evidence ID、usage、状态和失败原因；
- 支持按 event type 搜索和筛选；
- benchmark 页面可在同一 case 下切换 Direct / Fixed / Agentic。

页面不得从最终 outcome 反推不存在的步骤。只有配对的 started/completed 事件才画持续时间；事件缺失就显示“未记录”。旧 smoke 只能展示六个 outcome 的摘要，不能被包装成真实 Agent 轨迹。

CLI 入口定义为：

```text
vidsnap trace export RUN_OR_RESULT_DIR --output /absolute/path/trace.html
```

输出 HTML 把脱敏事件数据直接嵌入单个离线文件，不发起网络请求，也不要求旁边保留 RunBundle。只有用户显式选择包含 evidence thumbnails 时，才嵌入本地缩略图；benchmark 默认关闭。

## Benchmark 统一

当前 `FormalBenchmarkEngine` 单独实现了 planner、ASR、采样和最终回答，所以它绕过正式 `VideoHarness`，也无法产生完整轨迹。迁移后：

- `MCQTaskAdapter` 负责题目、选项、exact-match 解析和 MCQ verifier；
- Direct、Fixed、Agentic 分别选择对应 Execution Policy；
- 三组共用同一 Tool Plugin、Qwen provider、BudgetGuard、EventSink 和 usage 计量；
- `VariantOutcome` 与现有 report 字段由事件和最终结果投影得到；
- 每个 case/variant 的 RunBundle 写到仓库外的实验目录，git 永不包含视频、数据集、原始输出或结果；
- `pre_registered_tool_selection_alignment` 继续只比较外部 manifest 的人工预注册标签；
- smoke 仍只输出 `SMOKE_SUCCEEDED` / `SMOKE_FAILED` 和真实 usage projection，不产生优越性或非劣结论。

这个迁移只提高可比性和可观测性，不改变已注册的统计门槛，也不把基础设施验证包装成 Harness 优于 Direct 的实证结论。

## 错误与取消

- Tool 参数无效：该 call 记录为 failed；Agentic 可在剩余预算内做下一次合法决策。
- 未授权工具或越权参数：视为策略违规，立即 `FAILED`，不执行工具。
- 工具依赖缺失：run 开始前 `BLOCKED`，不进入模型循环。
- Provider 不可用：`BLOCKED`；provider 返回无效结构：一次格式修复后仍无效则 `FAILED`。
- 预算耗尽：`EXHAUSTED`，最后一个 `budget.updated` 必须说明耗尽维度。
- verifier 未通过：有 repair 预算则把结构化反馈送回循环，否则 `PARTIAL`。
- 取消：停止未完成调用、完成允许的清理；在现有 terminal contract 中写为 `FAILED` 且 reason 为 `cancelled`，不伪装成成功。临时 HTTP RunBundle 仍按现有规则删除。

所有失败事件都只包含脱敏类别和可操作的本地原因，不包含 provider body。

## 兼容与迁移

以下公共行为必须保持：

- `VideoHarness().run(source, goal, policy)` 签名不变；
- `HarnessPolicy.tool_mode` 默认仍为 `fixed`；
- Fixed 不增加 planner 调用，工具顺序保持 ASR → visual；
- CLI、SDK 和现有 HTTP 路由保持；
- `HarnessRunResult` 与现有 terminal states 保持；
- 现有 RunBundle 字段可继续读取；
- `SkillRegistry` 保留一个版本作为 `PluginRegistry` 的兼容 facade，但新代码不再向其中注册 `VideoHarness` 绑定方法；
- 现有一次性 `ToolPlan` 只保留为旧 benchmark manifest/reader 的兼容类型，不再驱动新的 Agentic runtime。

迁移完成后，`VideoHarness` 只负责组合默认 Kernel 与插件集合；具体 ASR、采样、任务解析和策略不再作为它的私有执行方法存在。

## 测试与完成标准

实现必须先写失败测试，再逐层变绿。完成标准如下：

1. **插件契约**：拒绝重复、缺依赖、循环依赖、未授权发现和无效 schema；第三方插件不在 allow-list 时不会装载。
2. **Agent 循环**：测试至少四条不同真实轨迹：只 ASR、只视觉、先视觉后 ASR、视觉后按新时间窗再次视觉；工具结果必须进入下一轮模型输入。
3. **权限与预算**：模型尝试未知工具、URL、模型、prompt 或超预算参数时，工具不会执行。
4. **Fixed 兼容**：现有 Fixed 测试全部保留，并断言无 planner call、顺序与终态不变。
5. **事件真实性**：每个 model/tool start 都有相同 correlation ID 的完成或失败事件；sequence 单调；敏感字段扫描无命中；未发生步骤没有事件。
6. **轨迹查看器**：使用真实 fixture RunBundle 验证 lane、顺序、配对 duration、失败状态和 summary-only 旧 run；不得使用推测事件。
7. **Benchmark 统一**：Direct、Fixed、Agentic 通过同一 Kernel；现有 outcome/report schema 与 smoke 结论规则继续通过。
8. **安全**：Hermes 凭据只进入 live 子进程；RunBundle、HTML、日志、报告和 git 的 secret scan 均无命中。
9. **发布门槛**：Ruff format/check、Mypy、完整 pytest、build、wheel smoke、conformance、secret scan 和 `git diff --check` 全部通过。

测试全部通过只代表“评测与轨迹基础设施已验证”。只有未来按预注册 formal protocol 得到真实统计结果后，才能讨论“Harness 是否优于 Direct”。

## 实施边界

这项改造按一个连续但可审核的计划实施：先建立事件与插件契约，再迁移两个内置工具和 Fixed，随后实现多步 Agentic，最后统一 benchmark 与加入静态轨迹导出。每一阶段都必须保持 Fixed 可运行和完整离线回归通过。

本设计完成后，下一步是单独编写 TDD 实施计划；在用户审阅并批准本文件之前，不开始实现。

## 参考启发

- DeepSeek Harness Architecture: <https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md>
- DeepSeek Harness Agent Loop: <https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent-loop/README.md>
- DeepSeek Harness Tools: <https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.md>
- DeepSeek Harness Trajectory UI: <https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/ui-trajectory/README.md>
