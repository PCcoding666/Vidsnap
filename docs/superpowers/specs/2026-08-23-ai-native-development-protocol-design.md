# VidSnap AI-native 开发协议设计

## 状态与结论

本设计为 VidSnap 仓库定义一套 repo-native 的 AI-native 开发协议：以 `PROJECT_STATE.md` 作为唯一项目状态源，把用户、Codex、Qoder CLI（Qwen3.8-Max 或 Kimi-K3）与 CI 的职责固化为可审计的流程，让每一项工作从立项到合并都有明确的目标、边界、证据和人工关口。本协议只改变开发协作方式，不改变 Harness 的产品架构，也不授权任何 live benchmark 或默认分支切换。

## 目标

1. 让 `PROJECT_STATE.md` 成为唯一项目状态源：当前主目标、各任务卡状态、阻塞原因与下一步人工关口全部在这一页可查。
2. 让每项工作以任务卡立项，包含 objective、non-goals、acceptance evidence、authority/data/secret boundaries、owner/executor/reviewer 与 next human gate 六个必填字段。
3. 固化角色分工：用户负责方向与合并决定，Codex 只做调度与验收，Qoder CLI 负责写代码，CI 独立验证，GitHub 保存长期事实。
4. 约束状态机为七个状态，任何状态变化都必须有依据并可回溯。
5. 保证一次只有一个主目标，执行模型不得自证完成。
6. 把协议落地拆成三批可独立审核的实施，并明确哪些仓库设置必须经用户授权。

## 非目标

- 不改动 `#7`、`#8`、`#9` 的现有记录：只在本协议中登记其存在与现状，不修改、不 merge。
- 不运行 live benchmark，不产生新的评测结论。
- 不提交视频、数据集、RunBundle、评测结果、凭据、原始 provider 请求或原始 provider 响应到 git。
- 不把基础设施验证（CI、secret scan、构建门槛）写成 Harness 性能结论。
- 不引入用户系统、认证、数据库、队列、前端或任何 SaaS 状态。
- 不自动执行 GitHub ruleset 配置、安全扫描开关或默认分支切换；这些只列为需用户授权的仓库设置。

## 角色与职责边界

| 角色 | 职责 | 明确不做 |
| --- | --- | --- |
| 用户 | 决定方向、批准任务卡、授权仓库设置、决定 merge | 不被任何模型输出替代决策 |
| Codex | 调度工作、拆解任务卡、审查代码与验收证据、更新状态 | 不自称实现完成，不代替 CI 结论 |
| Qoder CLI（Qwen3.8-Max 或 Kimi-K3） | 在独立 worktree 中按 TDD 分批写代码 | 不自证完成，不改状态机，不决定 merge |
| CI | 独立运行 lint、类型检查、测试、构建、wheel smoke、conformance 与 secret scan | 结果不被人工改写或绕过 |
| GitHub | 保存 issue、PR、CI 记录等长期事实 | 不保存凭据与大体积产物 |

核心约束：**执行模型不得自证完成。** Qoder 只能声明“已提交并等待验证”；完成与否由 Codex 审查加 CI 独立结果共同认定，最终由用户 merge 决定确认。一次只有一个主目标处于 `IN_PROGRESS`，其余目标必须处于 `PROPOSED`、`BLOCKED` 或已完结状态。

## 状态源与状态转换

`PROJECT_STATE.md` 是唯一项目状态源，位于仓库根目录，包含：

- 当前主目标及其任务卡编号；
- 任务卡列表：编号、objective、non-goals、acceptance evidence、authority/data/secret boundaries、owner/executor/reviewer、next human gate；
- 每张任务卡的状态与最近一次状态变更的原因；
- 需用户授权的仓库设置清单及其授权状态。

状态机只有七个状态，不允许其他取值：

```text
PROPOSED → APPROVED → IN_PROGRESS → READY_FOR_REVIEW → VERIFIED → RELEASED
              ↑            ↓                ↓
              └──────── BLOCKED ←──────────┘
```

- `PROPOSED`：任务卡已立项，等待用户批准方向。
- `APPROVED`：用户已批准，可进入实现；此时指定 executor。
- `IN_PROGRESS`：执行模型正在独立 worktree 中分批实现；Codex 审查不通过等普通返工也回到此状态。
- `READY_FOR_REVIEW`：全部批次已完成、完整本地 gate 通过，且已创建唯一的 Draft PR，等待 CI 结果。
- `VERIFIED`：Codex 各批审查通过且 Draft PR 触发的 CI 全绿，等待用户 merge 决定。
- `BLOCKED`：仅用于真实依赖、权限、外部条件或需要用户决定而无法继续的情况；必须写明阻塞原因与解除条件，普通审查失败不进入此状态。
- `RELEASED`：达到任务卡预先声明的最终集成目标并经用户批准，长期事实归档到 GitHub；stacked PR 合并到中间分支不自动等于公开发布。

`BLOCKED` 可从 `APPROVED`、`IN_PROGRESS`、`READY_FOR_REVIEW` 任一状态进入；解除后回到进入前的状态。状态变更必须同步写入 `PROJECT_STATE.md`，PR 描述引用对应任务卡编号。

## 主循环

每项工作按以下闭环推进：

1. **读取状态与任务卡**：Codex 与 Qoder 开始任何工作前，先读取 `PROJECT_STATE.md`，确认当前主目标与本任务卡状态。
2. **必要设计**：仅在任务卡涉及架构或公共契约变化时编写设计文档，放入 `docs/superpowers/specs/`，经用户批准后进入 `APPROVED`。
3. **独立 worktree**：Qoder 在独立 git worktree 中工作，不污染主工作区；分支名携带任务卡编号，全部批次共用同一分支。
4. **TDD 分批实现与批次提交**：Qoder 先写失败测试，再逐批变绿；每批通过对应的 focused local gate（该批相关测试与检查）后按批次提交，遵守 AGENTS.md 的命令与规则。
5. **Codex 逐批审查**：每批提交后由 Codex 审查代码质量、边界遵守情况与验收证据是否真实存在；不通过则回到 `IN_PROGRESS` 修复。
6. **完整本地 gate 与 Draft PR**：全部批次完成后跑完整本地 gate，通过后创建一个 Draft PR，任务卡进入 `READY_FOR_REVIEW`，PR 描述包含任务卡编号与 acceptance evidence。
7. **CI 独立验证**：由该 Draft PR 触发 CI，结果独立于任何人工判断；CI 全绿后任务卡进入 `VERIFIED`。
8. **用户决定 merge**：只有用户可以决定是否 merge；达到任务卡预先声明的最终集成目标并经用户批准后状态进入 `RELEASED`，并更新 `PROJECT_STATE.md`。
9. **更新状态**：每个状态转换同步写入 `PROJECT_STATE.md`，保持其为唯一事实源。

## 文件范围

本协议涉及的文件：

| 文件 | 用途 |
| --- | --- |
| `PROJECT_STATE.md` | 唯一项目状态源（新增） |
| `AGENTS.md` | 追加协议摘要与状态机约束（修改） |
| `CONTRIBUTING.md` | 追加任务卡与 PR 流程要求（修改） |
| `.github/ISSUE_TEMPLATE/*.yml` | issue form，强制任务卡六字段（新增） |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR 模板，要求任务卡编号与验收证据（新增） |
| `.github/workflows/ci.yml` | 修复 pull_request gate（修改） |
| `SECURITY.md` | 安全策略与禁止提交项（新增） |
| `.github/dependabot.yml` | 依赖更新配置（新增） |

## 三批实施

三批在同一个分支和同一个 Draft PR 内连续实施：每批只要求通过对应的 focused local gate 并经 Codex 审查，不要求每批单独开 PR 或单独等待远端 CI；全部批次完成后才跑完整本地 gate 并由唯一 Draft PR 触发远端 CI。

### 批次 A：状态页与协议

1. 创建 `PROJECT_STATE.md`，登记当前主目标、`#7`/`#8`/`#9` 的现状（只记录，不改不 merge）与本协议自身的任务卡。
2. 在 `AGENTS.md` 追加协议摘要：状态机七状态、一次一个主目标、执行模型不得自证完成、禁止提交的产物清单。
3. 在 `CONTRIBUTING.md` 追加任务卡六字段要求与主循环步骤。

### 批次 B：issue form 与 PR template

1. 新增 issue form，六个必填字段对应任务卡的 objective、non-goals、acceptance evidence、authority/data/secret boundaries、owner/executor/reviewer、next human gate。
2. 新增 PR 模板，要求填写任务卡编号、验收证据说明与 CI 预期。

### 批次 C：CI gate、SECURITY.md 与 Dependabot

1. 修复 `ci.yml` 的 pull_request gate：移除 base 分支限制，使所有 PR（无论目标分支）都触发 CI，保证 Draft PR 阶段即有独立验证。
2. 新增 `SECURITY.md`：声明禁止提交凭据、媒体、RunBundle、数据集、benchmark 结果、cookies、`.env` 与原始 provider 请求或响应；报告安全问题的渠道。
3. 新增 `.github/dependabot.yml`：对 GitHub Actions 与 pip 依赖启用定期更新检查。

## 需用户授权的仓库设置

以下事项只在 `PROJECT_STATE.md` 中登记为待授权，任何角色不得自动执行：

- GitHub ruleset（分支保护与合并规则）；
- 安全扫描开关（secret scanning、code scanning 等）；
- 默认分支切换。

用户逐项明确授权后才可配置，配置结果记录回 `PROJECT_STATE.md`。

## 失败处理

- **CI 失败**：任务卡保持 `READY_FOR_REVIEW` 不升级；Qoder 在同一 worktree 修复后重新触发 CI，不允许绕过或改写 CI 结论。
- **Codex 审查不通过**：写明原因，任务卡回到 `IN_PROGRESS` 修复后再次提交审查；普通审查失败不进入 `BLOCKED`。
- **外部依赖缺失**（凭据、权限、用户未批准、需要用户决定）：任务卡进入 `BLOCKED`，写明解除条件，不猜测、不模拟。
- **merge 被用户拒绝**：任务卡回到 `PROPOSED` 或 `BLOCKED`，按用户意见修改方向；已完成的代码保留在分支上不删除，除非用户明确要求。
- **状态冲突**：`PROJECT_STATE.md` 与实际分支/PR 状态不一致时，以调查后的事实为准更新状态页，并在 PR 中说明修正原因。
- **边界违规**：任何试图提交禁止产物或把基础设施验证写成性能结论的行为，立即终止该批次并报告用户。

## 测试与完成标准

本协议是文档与配置类改造，完成标准如下：

1. `PROJECT_STATE.md` 存在且包含主目标、全部任务卡字段、七状态取值与变更原因栏。
2. `AGENTS.md` 与 `CONTRIBUTING.md` 的追加内容与本协议一致，不删除现有规则。
3. issue form 的六个必填字段齐全，PR 模板包含任务卡编号与验收证据两栏。
4. `ci.yml` 修改后，任意目标分支的 PR 都触发 CI；现有 push 行为不变。
5. `SECURITY.md` 列出全部禁止提交项；`.github/dependabot.yml` 覆盖 GitHub Actions 与 pip。
6. 三批共用的同一个 Draft PR 通过现有 CI 全部步骤（lint、mypy、pytest、build、wheel smoke、conformance、secret scan、`git diff --check`）。
7. `#7`/`#8`/`#9` 在本协议实施前后保持原样，无代码改动、无 merge。
8. 文档与配置中不出现 TBD、待定或空承诺。

## 迁移边界

- 本协议生效后，所有新工作从任务卡开始；存量未立项的工作在下次触碰前补建任务卡。
- `#7`、`#8`、`#9` 只在 `PROJECT_STATE.md` 中记录现状，不改动、不 merge，直至用户单独立项。
- 默认分支在用户授权切换前仍为 `vidsnap_slim`，CI 与 PR 流程按现状运行。
- 协议文档本身（本文件）属于设计记录，不随批次实施修改；实施偏差记录在 `PROJECT_STATE.md`，不回改本文件。
- 本协议不改变 Harness 的模型固定（qwen3.8-max）、并发上限（2）与凭据仅来自本机环境变量的既有约束。
