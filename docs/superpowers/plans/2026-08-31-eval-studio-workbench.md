# Eval Studio Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在完全不改动现有 `vidsnap trace export`、RunBundle、契约与门禁的前提下，新增 `vidsnap studio export MANIFEST -o eval-studio.html`：把外部预注册清单与本地 RunBundle 投影成一个自包含、离线、脱敏、可键盘访问的 Eval Studio HTML（迭代工作台 + 探索工作台）。

**Architecture:** 新增 `src/vidsnap/studio/`：严格清单契约（`vidsnap.studio/v1`）→ 只读投影（复用 `vidsnap.trace.read_trace`）→ 打包模板渲染单文件 HTML。缺失字段一律“未记录”，合成夹具显式 `SYNTHETIC`，失败路径一律退出码 2 且不写输出。

**Tech Stack:** Python 3.10+、Pydantic 2（`StrictModel`，`extra="forbid"`）、Typer、pytest、Ruff、Mypy、Hatchling `force-include`。

**Spec:** `docs/superpowers/specs/2026-08-31-eval-studio-workbench-design.md`

**Test runner:** 本仓库无预装环境时以 `PYTHONPATH=src python3 -m pytest` 运行；若存在项目 venv，则用 venv 内等价命令。所有命令都必须在仓库根目录执行。

## Global Constraints

- 只读 RunBundle：导出过程永不写入、移动或修改任何 RunBundle、清单或用户数据。
- 所有真实字段只能来自 RunBundle 投影或预注册清单；缺失一律“未记录”，禁止发明工具调用、时长、评分或证据。
- 输出为单文件离线 HTML：无 `https://`、`fetch(`、`WebSocket`、远程 `src`/`href`、遥测。
- 合成内容必须带 `synthetic: true` 且页面渲染 `SYNTHETIC` 徽章；五个演示 approach（Simple prompt / A bigger model / Adaptive thinking / A better prompt / Generate evaluate repair）只是夹具标签。
- 导出不得包含 API key、`Authorization`、provider 原始请求/响应、链式思考、内部推理、本机绝对路径或 provider 身份。
- 拒绝任何已存在的输出路径（含空文件、目录、符号链接）；先校验与投影，经同目录临时文件 + fsync 后以原子 no-replace 方式发布，失败不留半成品。
- `vidsnap trace export` 与现有全部命令、契约、模板、门禁保持不变。
- 每个任务按 RED → GREEN → focused regression → 审阅检查点执行；不得夹带无关重构。

---

## File Map

### 新增

- `src/vidsnap/studio/__init__.py`：稳定导出（`StudioManifest`、`load_studio_manifest`、`StudioDocument`、`project_studio`、`export_studio`）。
- `src/vidsnap/studio/manifest.py`：`vidsnap.studio/v1` 严格清单模型与校验（版本序列、身份唯一、引用安全）。
- `src/vidsnap/studio/project.py`：清单 + RunBundle → 冻结 `StudioDocument`（复用 `read_trace`）。
- `src/vidsnap/studio/export.py`：模板装载、脚本安全内联、覆盖拒绝、一次性写入。
- `src/vidsnap/studio/assets/studio.html`：零远程引用的工作台模板（标签页、矩阵、模态框、ARIA）。
- `src/vidsnap/studio/assets/studio.js`：内联交互脚本（标签页/矩阵/试验导航，纯本地）。
- `src/vidsnap/studio/assets/synthetic_exploration.json`：五个演示 approach 的打包合成夹具（`synthetic: true`）。
- `tests/studio/conftest.py`：真实 `RunBundle.create` + `TraceRecorder` 搭建的迭代/探索夹具。
- `tests/studio/test_studio_manifest.py`
- `tests/studio/test_studio_projection.py`
- `tests/studio/test_studio_security.py`
- `tests/studio/test_studio_synthetic.py`
- `tests/studio/test_studio_export.py`
- `tests/studio/test_studio_ui.py`
- `tests/studio/test_studio_distribution.py`

### 修改

- `src/vidsnap/cli.py`：新增 `studio` 子命令族与 `studio export`；不动其它命令。
- `pyproject.toml`：`force-include` 新增 `vidsnap/studio/assets/*` 三个条目。
- `tests/test_cli.py`：仅追加三个测试（帮助显示 `studio`、覆盖拒绝、`trace export` 兼容）。

---

### Task 1: Studio 清单严格契约

**Files:**
- Create: `src/vidsnap/studio/__init__.py`（可先只导出清单层）
- Create: `src/vidsnap/studio/manifest.py`
- Create: `tests/studio/test_studio_manifest.py`

**Interfaces:**
- Produces: `StudioManifest`、`StudioVersion`、`StudioCase`、`StudioTrial`、`StudioApproach`、`StudioProblem`、`StudioEval`。
- Consumes: `vidsnap.contracts.models.StrictModel`。

- [ ] **Step 1: 写 RED 测试（契约与身份规则）**

覆盖：`api_version` 必须为 `vidsnap.studio/v1`；未知字段拒绝；版本必须 `v0..vN` 连续且唯一；`iteration` 与 `exploration` 至少存在其一；同一 version 内 `case_id` 重复拒绝；同一 `case_id` 可跨 version 出现以支持 v0/v1 对比；同一 `(version, case_id)` 内 `trial_id` 重复拒绝；因此 `(version, case_id, trial_id)` 三元组全局唯一。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_manifest.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'vidsnap.studio'`。

- [ ] **Step 3: GREEN —— 最小实现**

全部模型继承 `StrictModel`；`version` 模式 `^v[0-9]+$`；`@model_validator` 校验序列连续与身份唯一；错误信息类别化，不回显敏感值。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio -q` 与 `ruff format --check src tests && ruff check .`

- [ ] **Step 5: 审阅检查点**：确认没有触碰 `vidsnap.trace` 与任何现有契约。

### Task 2: 运行引用安全与加载器

**Files:**
- Modify: `src/vidsnap/studio/manifest.py`（引用规则）
- Create: `src/vidsnap/studio/manifest.py` 中的 `load_studio_manifest(path) -> StudioManifest`
- Modify: `tests/studio/test_studio_manifest.py`

- [ ] **Step 1: 写 RED 测试（引用安全）**

覆盖：相对路径解析后必须位于 manifest root（含符号链接逃逸用例）；`..`、绝对路径、`\\`、`http://`、`file://`、`data:` 一律拒绝；引用的目录缺少 `manifest.json` 时 `load_studio_manifest` 抛 `ValueError`；合法引用成功装载。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_manifest.py -q`

Expected: FAIL（新函数/规则不存在，`ImportError` 或断言失败）。

- [ ] **Step 3: GREEN**

先做字符串规则校验，再 `resolve()` 后 `is_relative_to(root)`；装载器读文件 → `StudioManifest.model_validate_json` → 逐引用检查目标含 `manifest.json`。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio -q`

- [ ] **Step 5: 审阅检查点**：确认越权路径没有触发任何文件系统写入。

### Task 3: 真实投影（版本 × 案例 × 试验 → RunBundle）

**Files:**
- Create: `src/vidsnap/studio/project.py`
- Create: `tests/studio/conftest.py`（用 `RunBundle.create` + `TraceRecorder` 建真实夹具）
- Create: `tests/studio/test_studio_projection.py`

- [ ] **Step 1: 写 RED 测试**

覆盖：每个 (version, case, trial) 的 `run_id`、终态、事件序列与 `read_trace(对应 RunBundle)` 精确一致；未记录的 usage/时长/验证结果为 `None` 且投影标记“未记录”；`held_out` 案例进入 held-out 分组；探索侧对比指标（通过次数、违规、令牌、延时）只取自已记录计数；Answer/Evidence/Trace/Verifier 四面板数据结构存在且内容等于账本记录。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_projection.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'vidsnap.studio.project'`。

- [ ] **Step 3: GREEN**

`project_studio(manifest_path) -> StudioDocument`：逐引用调用 `read_trace`；冻结模型；缺失字段保持 `None`；`limitations` 汇总只读失败类别（不含路径之外的敏感信息）。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio tests/trace -q`

- [ ] **Step 5: 审阅检查点**：确认投影零写入、零网络。

### Task 4: 安全剥离

**Files:**
- Modify: `src/vidsnap/studio/project.py`（投影边界脱敏复核）
- Create: `tests/studio/test_studio_security.py`

- [ ] **Step 1: 写 RED 测试**

构造账本/清单携带：`api_key`、`Authorization: Bearer`、provider 原始响应体、`chain_of_thought`/`internal_reasoning`、`/Users/…` 绝对路径、provider 模型名与 base_url。断言 `project_studio` 输出及其 JSON 序列化中全部不命中；答案文本仅来自 `result.json` 受控投影。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_security.py -q`

Expected: FAIL（投影层尚未实现对应断言路径）。

- [ ] **Step 3: GREEN**

复用 `vidsnap.trace.reader` 的既有脱敏；在 studio 层增加对清单字符串字段的同规则过滤与绝对路径剥离。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio -q && PYTHONPATH=src python3 scripts/secret_scan.py`

- [ ] **Step 5: 审阅检查点**：逐条核对设计文件“真实性与脱敏规则”。

### Task 5: 打包合成夹具（SYNTHETIC）

**Files:**
- Create: `src/vidsnap/studio/assets/synthetic_exploration.json`
- Create: `tests/studio/test_studio_synthetic.py`

- [ ] **Step 1: 写 RED 测试**

覆盖：打包夹具可被 `StudioManifest` 校验；五个演示 approach 标签恰好为 Simple prompt / A bigger model / Adaptive thinking / A better prompt / Generate evaluate repair；所有夹具节点 `synthetic: true`；夹具不引用任何真实路径。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_synthetic.py -q`

Expected: FAIL with `FileNotFoundError`/资源缺失。

- [ ] **Step 3: GREEN**

写入夹具（指标全部 `null` 或明确合成标记，绝不冒充真实测量）。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio -q`

- [ ] **Step 5: 审阅检查点**：确认夹具文本不含“结论性”措辞。

### Task 6: 单文件 HTML 导出

**Files:**
- Create: `src/vidsnap/studio/assets/studio.html`（含唯一数据标记 `__VIDSNAP_STUDIO_JSON__`）
- Create: `src/vidsnap/studio/assets/studio.js`
- Create: `src/vidsnap/studio/export.py`
- Create: `tests/studio/test_studio_export.py`

- [ ] **Step 1: 写 RED 测试**

覆盖：导出为单文件且不含 `https://`、`fetch(`、`WebSocket`、远程 `src`/`href`；内联数据脚本唯一且 `StudioDocument` 回读相等；脚本安全转义（`</script>` 注入不越狱）；任何已存在输出（含空文件、目录、符号链接）拒绝覆盖且原内容不变；检查与发布之间并发创建的输出不被覆盖；悬空引用在写文件前失败。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_export.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'vidsnap.studio.export'`。

- [ ] **Step 3: GREEN**

仿照 `vidsnap/trace/export.py`：模板经 `importlib.resources` 装载、标记计数校验、`ensure_ascii=True` + `<` → `\u003c`、先校验后写。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio tests/trace -q`

- [ ] **Step 5: 审阅检查点**：确认 `trace export` 模板与代码零改动。

### Task 7: UI 结构与可访问性

**Files:**
- Modify: `src/vidsnap/studio/assets/studio.html` / `studio.js`
- Create: `tests/studio/test_studio_ui.py`

- [ ] **Step 1: 写 RED 测试**

覆盖（对导出 HTML 的静态结构断言）：迭代三标签页与探索三标签页的 `role=tablist/tab/tabpanel` 与 `aria-selected` 初始状态；矩阵单元格为 `<button>` 且 `aria-label` 含版本/案例/试验信息；`role=dialog` + `aria-modal` 钩子；版本选择器、差异导航（prev/next）、试验导航的数据属性存在；探索对比表含通过次数、违规、令牌、延时列；`SYNTHETIC` 徽章渲染；“未记录”文案渲染。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_ui.py -q`

Expected: FAIL（模板尚未具备相应结构）。

- [ ] **Step 3: GREEN**

实现模板交互：方向键标签页切换、单元格→抽屉→模态框、`Esc` 关闭并归还焦点、版本/差异/试验导航；所有状态更新同步 ARIA。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/studio -q`

- [ ] **Step 5: 审阅检查点**：纯键盘走查矩阵→试验详情→返回路径。

### Task 8: CLI 边界（增量）

**Files:**
- Modify: `src/vidsnap/cli.py`
- Modify: `tests/test_cli.py`（仅追加）

- [ ] **Step 1: 写 RED 测试**

追加到 `tests/test_cli.py`：`--help` 列出 `studio`；`studio export` 对已存在输出退出码 2 且原内容不变；`trace --help` 仍列出 `export` 且无 `studio` 相关行为变化。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/test_cli.py -q`

Expected: FAIL（`studio` 子命令不存在）。

- [ ] **Step 3: GREEN**

新增 `studio_app` 与 `studio export MANIFEST -o OUTPUT`；失败统一退出码 2、类别化信息；成功回显输出绝对路径。

- [ ] **Step 4: 回归**

Run: `PYTHONPATH=src python3 -m pytest tests/test_cli.py tests/studio -q`

- [ ] **Step 5: 审阅检查点**：确认未改动任何既有命令的参数与输出。

### Task 9: 分发资产

**Files:**
- Modify: `pyproject.toml`（`force-include` 追加三个 `vidsnap/studio/assets/*` 条目）
- Create: `tests/studio/test_studio_distribution.py`

- [ ] **Step 1: 写 RED 测试**

仿照 `tests/test_distribution_assets.py`：构建 wheel 后断言包含 `vidsnap/studio/assets/studio.html`、`studio.js`、`synthetic_exploration.json`；studio 资产中无媒体与敏感文件名。

- [ ] **Step 2: 确认 RED**

Run: `PYTHONPATH=src python3 -m pytest tests/studio/test_studio_distribution.py -q`

Expected: FAIL（wheel 缺少条目）。

- [ ] **Step 3: GREEN**：补齐 `force-include`。

- [ ] **Step 4: 回归（全量门禁）**

Run: `ruff format --check src tests scripts && ruff check . && mypy src && PYTHONPATH=src python3 -m pytest -q && python3 -m build && PYTHONPATH=src python3 -m vidsnap conformance && python3 scripts/secret_scan.py && git diff --check`

- [ ] **Step 5: 最终审阅检查点**：与设计文件逐条对账，确认 `vidsnap trace export` 行为不变。

---

## 执行状态

以上 Tasks 1-9 的 RED→GREEN 步骤保留为执行记录；全部任务已按 TDD 完成（每批先写失败测试、记录失败原因，再实现至通过）：

- Tasks 1-2：studio manifest 严格契约与运行引用安全（`vidsnap.studio/v1`）；
- Tasks 3-4：真实投影（`project_studio` → 冻结 `StudioDocument`，`vidsnap.studio.projection/v1`）与安全剥离；
- Task 5：打包合成夹具（五个演示 approach，全部 `synthetic: true`）；
- Tasks 6-7：单文件离线 HTML 导出与 UI 结构/可访问性；
- Tasks 8-9：`vidsnap studio export` CLI 边界与 wheel/sdist 分发。

状态约束：

- 最终门禁仍由 Codex 独立复跑确认；本计划工作未提交、未推送、未 merge；
- 浏览器中看到的演示样例是 SYNTHETIC 夹具，不是 live benchmark，也不构成任何性能或优越性结论。
