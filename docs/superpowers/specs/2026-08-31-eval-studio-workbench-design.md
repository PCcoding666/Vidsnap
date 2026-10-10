# Eval Studio Workbench 设计

## 状态与结论

本设计把 VidSnap 现有的静态轨迹/基准查看器演进为一个真实、本地、可离线打开的 **Eval Studio**：它不产生任何新数据，只把已存在的 RunBundle 与一份外部预注册清单（studio manifest）投影成单文件 HTML 工作台。参考对象是一个 prompting workbench 风格的产品演示，但 VidSnap 的价值定位不变：本地优先、证据接地、预算受限、事件可回放；不是 SaaS 前端。

已确认的主方向：

- 新增两个工作台：**既有 Agent 迭代工作台**（Prompt / Evals / Held-out 三个标签页）与**新 Agent 探索工作台**（Problem / Approaches / Eval 三个标签页）；
- 所有真实字段只能来自两类来源：本地 RunBundle 事件账本，以及操作者手写的预注册 studio manifest；缺失数据一律渲染为“未记录（not recorded）”，永不合成；
- 合成示例（探索工作台的五个演示 approach）只作为打包夹具存在，且页面必须显眼标注 `SYNTHETIC`；
- 输出是一个自包含、零网络请求的静态 HTML；不引入 React、Vite、FastAPI 服务、账号、数据库、远程资源或遥测；
- Direct、Fixed、Agentic 保持为可选的基准预设，本设计不强制任何运行进入同一序列；
- CLI 只增加一个子命令族：`vidsnap studio export MANIFEST -o eval-studio.html`，不改动 `vidsnap trace export` 的任何行为。

本文件只定义架构与验收标准，不包含任何 live 模型结论，也不授权新的基准运行。

## 为什么要改

当前 `vidsnap trace export` 只能查看单个 RunBundle（或一个 Direct/Fixed/Agentic case 目录）的轨迹。它回答“这一次运行发生了什么”，但无法回答评测工作中的真实问题：

- 同一个 agent 的 prompt 从 v0 改到 v3，哪些 case 变好、哪些变坏？
- 每个版本、每个 case、每次试验（trial）的证据链分别在哪里？
- 从零探索一个新任务时，几种候选 approach 在受限预算下的通过数、违规、令牌与延时各是多少？

这些问题的答案都已经存在于本地 RunBundle 里；缺的只是一个把它们按“版本 × 案例 × 试验”组织起来的只读投影。本设计补齐这一层，且严格遵守仓库既有的真实性约束：查看器永远是事件账本的投影，不得从结果反推不存在的步骤。

## 用户旅程

### 旅程一：既有 Agent 迭代（iteration workspace）

1. 操作者已经用同一任务在多组 prompt 版本上跑过若干本地运行，每次运行产生一个 RunBundle；
2. 操作者手写（或用脚本生成）一份 `studio.json` 预注册清单，声明版本号 `v0..vN`、每个版本包含的 case、每个 case 的多次试验，以及每次试验指向的 RunBundle 相对路径；
3. 运行 `vidsnap studio export studio.json -o eval-studio.html`；
4. 打开 HTML，看到三个标签页：
   - **Prompt**：版本列表（v0…vN）、每个版本的变更摘要、相邻版本之间的 before/after 差异（可前后导航的差异模态框）；
   - **Evals**：版本 × 案例评测矩阵；一个单元格包含该版本该案例的全部试验；点击单元格打开试验列表，点击试验进入试验详情；
   - **Held-out**：与 Evals 结构相同，但数据来自清单中标记为保留集（held-out）的 case；缺失同样渲染为“未记录”；
5. 试验详情页提供 Answer / Evidence / Trace / Verifier 四个面板与试验间前后导航；每个面板只投影已记录事实；
6. 所有 provenance 区块只区分两种状态：来自 RunBundle 的记录值（缓存/离线），或“未记录”。永不出现虚构的来源标注。

### 旅程二：新 Agent 探索（exploration workspace）

1. 操作者在清单中声明一个问题（Problem：目标 + 一组丰富约束）和若干候选 approach；
2. 每个 approach 卡片展示：标签、（可选的）prompt 摘要/哈希、受限 harness 配置（预算、工具白名单）、以及指向其试验 RunBundle 的引用；
3. **Eval** 标签页给出对比表：每个 approach 的通过次数、违规次数、令牌用量、延时——全部只从 RunBundle 已记录计数投影；
4. 打包夹具提供五个演示 approach：`Simple prompt`、`A bigger model`、`Adaptive thinking`、`A better prompt`、`Generate evaluate repair`。它们是**合成夹具标签，不是普适结论**；页面必须以 `SYNTHETIC` 徽章显示其来源，且任何指标若未记录则显示“未记录”。

## 数据边界

```
┌────────────────────────────┐      ┌──────────────────────────────┐
│ studio.json（操作者预注册） │      │ RunBundle（write-once 账本）  │
│ 版本/案例/试验/运行引用     │      │ manifest/events/evidence/…   │
└─────────────┬──────────────┘      └───────────────┬──────────────┘
              │ 严格校验（vidsnap.studio/v1）        │ read_trace 投影
              └───────────────┬─────────────────────┘
                              ▼
                StudioDocument（只读、脱敏、冻结）
                              ▼
             单文件 eval-studio.html（内联 JSON + 内联 JS）
```

- **唯一写入口**：`vidsnap studio export`。它不写 RunBundle、不写清单、不产生任何新的运行数据；
- **唯一读入口**：清单经 `load_studio_manifest` 严格校验后，由投影层调用既有 `vidsnap.trace.read_trace` 读取每个被引用的 RunBundle；
- **RunBundle 永不修改**：导出过程对 RunBundle 只读，且默认不读取 `artifacts/` 二进制字节（与 `trace export` 默认行为一致）；
- **没有网络**：导出过程不发起任何网络请求；生成的 HTML 不引用任何远程资源。

## 外部预注册清单（studio manifest）

清单是操作者在运行发生之前或之后手写的 JSON，`api_version` 固定为 `vidsnap.studio/v1`，使用与全仓库一致的 `StrictModel`（`extra="forbid"`）校验。清单文件所在目录称为 **manifest root**；所有运行引用都相对于它解析。

```jsonc
{
  "api_version": "vidsnap.studio/v1",
  "title": "可选的人类可读标题",
  "iteration": {                      // 可选：迭代工作台
    "agent_id": "video-summarizer",
    "versions": [
      {
        "version": "v0",              // 必须是 v0..vN，严格递增、无重复、无跳号
        "summary": "基线 prompt",      // 版本变更摘要（人类预注册）
        "prompt": "可选，操作者自愿公开的 prompt 文本",
        "prompt_sha256": "64 位十六进制，可选",
        "cases": [
          {
            "case_id": "case-01",
            "held_out": false,        // 默认 false；true 进入 Held-out 标签页
            "video_sha256": "64 位十六进制，可选",
            "trials": [
              { "trial_id": "t1", "run": "runs/v0/case-01/t1" }
            ]
          }
        ]
      }
    ]
  },
  "exploration": {                    // 可选：探索工作台
    "problem": {
      "statement": "任务描述",
      "constraints": ["约束 1", "约束 2"]
    },
    "approaches": [
      {
        "id": "simple-prompt",
        "label": "Simple prompt",
        "synthetic": true,            // 合成夹具必须显式为 true
        "prompt_sha256": "可选",
        "harness": {                  // 受限配置，只允许预算与工具白名单字段
          "max_model_calls": 12,
          "max_tool_calls": 6,
          "tools": ["transcribe_audio", "sample_evidence"]
        },
        "trials": [ { "trial_id": "t1", "run": "runs/simple-prompt/t1" } ]
      }
    ]
  },
  "evals": [                          // 可选：预注册评测定义
    { "id": "verifier-pass", "description": "RunBundle verifier 记录为通过" }
  ]
}
```

### 引用与身份规则

- `version` 必须匹配 `^v[0-9]+$`，且必须从 `v0` 起严格连续递增；
- 同一 `case_id` 可出现在不同版本中，用于比较同一案例在 v0 与 v1 等版本下的表现；但 `case_id` 在**同一 version 内唯一**，`trial_id` 在同一 `(version, case_id)` 内唯一，因此 **(version, case_id, trial_id) 三元组全局唯一，禁止重复身份**；探索侧同理，`(approach_id, trial_id)` 唯一；
- `run` 必须是 manifest root 内的**相对 POSIX 路径**；禁止绝对路径、`..`、反斜杠、URL scheme（`http://`、`file://`、`data:` 等一律拒绝）；解析后必须仍位于 manifest root 之下（containment 双重校验：先字符串规则，再 `resolve()` 后 `is_relative_to`）；
- 引用的目标目录必须是一个可读的 RunBundle（含 `manifest.json`）。引用悬空或逃逸属于**清单错误**，导出直接失败（见“失败行为”）；
- 清单内任何字段都不允许携带凭据；校验层对明显的密钥形态（`api_key`、`Authorization`、`Bearer ` 等）直接拒绝。

## 真实性与脱敏规则（truth & redaction）

1. **投影即边界**：所有展示值都来自 `StudioDocument`——由 `read_trace` 投影与清单字段合成的冻结只读结构。模板渲染层不做任何“补全”。
2. **未记录即未记录**：缺失的时长、令牌、通过状态、证据、哈希一律渲染为“未记录 / not recorded”。禁止用 0、空串或占位符冒充已记录值（0 只有在事件账本里真实记录为 0 时才显示为 0）。
3. **复用既有脱敏**：轨迹投影复用 `vidsnap.trace.reader` 的敏感键删除、路径脱敏与字符串规则；studio 层额外保证：
   - 不出现 API key、`Authorization`、cookie、provider 原始请求/响应；
   - 不出现链式思考、内部推理、scratchpad 类字段；
   - 不出现本机绝对路径（`/Users/…`、`/home/…` 等）——运行引用在投影中只保留 manifest root 内的相对形式；
   - provider identity 保持 `read_trace` 的既有结果（“configured (identity redacted)”或“未记录”），不透出模型名、base_url 或供应商身份；
   - 最终结构化答案文本仅通过 `result.json` 的既有受控投影展示。
4. **合成即标注**：任何来自打包夹具而非真实 RunBundle 的内容，其数据节点必须携带 `synthetic: true`，页面必须渲染显眼的 `SYNTHETIC` 徽章；合成夹具不得引用真实数据路径。
5. **provenance 二态**：每个试验的 provenance 区块只有两种取值——记录自 RunBundle 的字段（含 run_id、bundle 文件哈希存在的字段），或“未记录”。不存在第三种“看起来像来源”的状态。

## UI 状态与交互

### 结构

- 顶部工作区切换：`Iteration` / `Exploration`（只渲染清单中存在的工作区；两者都缺则导出失败）；
- **迭代工作台**：`Prompt`、`Evals`、`Held-out` 三个标签页；版本选择器（v0…vN）贯穿 Evals/Held-out 矩阵；
- **探索工作台**：`Problem`、`Approaches`、`Eval` 三个标签页；Approaches 为卡片布局；Eval 为对比表（通过次数、违规、令牌、延时）。

### 迭代矩阵与试验

- 评测矩阵：行 = 案例，列 = 选定版本下的试验位；单元格按钮显示已记录的通过/失败/未记录状态与试验计数；
- 点击单元格 → 试验列表抽屉；点击试验 → 试验详情模态框，含四个面板：
  - **Answer**：`result.json` 受控投影的结构化答案；
  - **Evidence**：`TraceEvidence` 投影；当且仅当清单或账本明确记录了缩略图/转录片段引用时展示缩略图或 transcript span，否则“未记录”；
  - **Trace**：按 Input / Model / Tools / Verifier lane 的事件序列，含预算计数器、受限插件名与参数、真实测得的 duration；
  - **Verifier**：verifier 门与终态记录；
- 试验详情内提供上一个/下一个试验导航，以及返回列表。

### 版本差异

- Prompt 标签页列出每个版本的变更摘要；“查看差异”打开 before/after 模态框，显示相邻版本（vN-1 → vN）的摘要与（如操作者提供了文本）prompt 文本差异；
- 差异模态框支持前后导航（v1→v0、v2→v1 …… 依次切换）；缺少 prompt 文本时差异区显示“未记录”，只显示已预注册的摘要。

### 可访问性（accessibility）

- 标签页使用 `role="tablist" / tab / tabpanel`，`aria-selected`、`aria-controls` 状态正确，支持左右方向键切换；
- 矩阵单元格是真实 `<button>`，`aria-label` 含版本、案例、试验数与状态摘要；
- 模态框/抽屉使用 `role="dialog"`、`aria-modal="true"`，`Esc` 关闭并把焦点还给触发元素；
- 版本切换、差异导航、试验导航都可通过纯键盘完成；所有交互控件有可见焦点样式；
- `SYNTHETIC` 徽章与“未记录”状态既是视觉标记，也带文本（非纯颜色表达）。

## CLI 边界

```text
vidsnap studio export MANIFEST -o eval-studio.html
```

- **纯增量**：新增 `studio` 子命令族；`vidsnap trace export`、`analyze`、`demo`、`benchmark`、`recipe`、`plugin` 全部不变；
- 参数：`MANIFEST`（存在的文件）与 `-o/--output`（目标 HTML）；
- **拒绝任何已存在的输出路径**（含空文件、目录、符号链接；`FileExistsError` → 退出码 2，既有内容保持原样）；完整 HTML 先写同目录临时文件并 fsync，最终以原子 no-replace 方式发布，不覆盖并发创建的文件；
- 成功后只回显导出文件绝对路径；失败时输出脱敏的类别化原因，退出码 2，不回显清单内容或路径之外的敏感信息。

## 兼容性

- `vidsnap trace export` 的行为、输出与模板保持不变；现有 `tests/trace/*` 全部继续通过；
- 现有公共契约（`TraceDocument`、RunBundle 格式、`StrictModel` 家族）不做语义变更；studio 层只消费它们；
- RunBundle `vidsnap.run/v1` 与 `vidsnap.trace/v1` 不变；新增投影使用独立版本号 `vidsnap.studio/v1`（清单）与 `vidsnap.studio.projection/v1`（嵌入文档），互不影响旧格式；
- wheel 打包沿用 `force-include` 机制，仅新增 `vidsnap/studio/assets/*` 条目；
- 不改变任何门禁（ruff、mypy、pytest、build、conformance、secret scan、`git diff --check`）的含义与阈值。

## 失败行为

| 情形 | 行为 |
| --- | --- |
| 清单不存在/不是 JSON/结构不合法/含未知字段 | 退出码 2，类别化错误；不写输出 |
| 版本序列非法（非 `v0..vN` 连续）或身份重复 | 退出码 2，指明违规类别（不含敏感值） |
| 运行引用含 `..`、绝对路径、URL scheme，或解析后逃逸 manifest root | 退出码 2，拒绝导出 |
| 引用目录不存在 / 缺少 `manifest.json` / 事件账本不可读 | 退出码 2（悬空引用是清单错误，不允许渲染成“看起来空”的工作台） |
| RunBundle 合法但内部字段缺失（无 usage、无 duration、无 verifier 记录） | 成功导出；对应字段渲染“未记录” |
| 输出路径已存在（含空文件、目录、符号链接） | 退出码 2，既有内容保持原样 |
| 清单同时缺少 `iteration` 与 `exploration` | 退出码 2 |

所有失败路径都不允许部分写出输出文件（先校验与投影，最后一次性原子写入）。

## 测试策略

全部离线、确定性、无网络、无模型调用：

1. **清单契约**：严格校验、未知字段拒绝、版本序列规则、(version, case, trial) 重复身份拒绝；
2. **引用安全**：`..`、绝对路径、URL、符号链接逃逸均被拒绝；合法相对路径解析后仍在 root 内；
3. **投影真实性**：使用真实 `RunBundle.create` + `TraceRecorder` 夹具，断言版本/案例/试验与 RunBundle 的精确映射；缺失字段为“未记录”且无发明值；
4. **合成标注**：打包夹具的五个演示 approach 在数据与页面中都带 `SYNTHETIC`；
5. **安全剥离**：构造携带密钥、provider 原始响应、内部推理、绝对路径的账本，断言导出 HTML 无一命中；
6. **HTML 形态**：单文件、无 `https://` / `fetch(` / 远程引用；单一内联数据脚本且与投影相等；脚本安全转义；拒绝任何已存在输出（含空文件），检查与发布之间的并发创建不被覆盖；
7. **结构与可达性**：标签页/矩阵/模态框的 ARIA 角色与状态、键盘导航钩子、版本差异导航、试验导航的静态结构断言；
8. **CLI**：`--help` 显示 `studio`；`studio export` 覆盖拒绝；`trace export` 帮助与行为不变；
9. **分发**：构建后的 wheel 包含 `vidsnap/studio/assets/*`；
10. **回归**：每个批次结束运行全量离线套件。

## 非目标

- 不构建服务端、账号、数据库、队列、任务历史或前端工程（React/Vite）；
- 不在 UI 中编辑 prompt、运行新实验、切换 provider/model/base_url；
- 不把 Direct、Fixed、Agentic 强加给所有运行；它们只是可选基准预设；
- 不合成工具调用、时长、输出、评分或证据；不从结果反推未记录的步骤；
- 不引入远程资源、遥测、任意 URL 或第三方前端依赖；
- 不修改既有 RunBundle、轨迹模板、基准脚本或发布门禁的语义。

## 实现状态

- 本设计的实现（清单契约、只读投影、合成夹具、单文件导出、UI 资产、CLI 与打包）已落在当前独立 worktree 中，全部遵守上述边界：本地、离线、只读 RunBundle、无网络、无新运行数据。
- 本设计不产生、也不授权任何 live benchmark；目前不存在任何"Harness 优于 Direct"或模型能力结论。探索工作台的五个演示 approach 是合成夹具标签（`SYNTHETIC`），不是测量结果。

## 已知设计关切

- **悬空引用按错误处理而非“未记录”**：清单引用的是运行实体本身；实体缺失说明清单与磁盘不一致，渲染成空单元格会诱导误读。字段级缺失才是“未记录”。
- **prompt 文本可选**：差异模态框在操作者未提供 prompt 文本时退化为摘要对比，避免迫使操作者把 prompt 写入清单。
- **令牌与延时只在 `provider_reported` 为真且账本有记录时显示**；否则“未记录”，防止把 0 当真实零值。
