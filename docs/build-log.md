# Build Log · 公开构建日志

> VidSnap 由一个自主 AI 工程循环持续迭代(glass-box 到开发过程本身)。
> 每个 cycle:选一面透镜 → 对抗性自审 → 修最高杠杆的一件事 → 机检发版 → 记录于此。
> This project is iterated by an autonomous AI engineering loop; each cycle picks a lens, red-teams the product, ships one high-leverage fix, and logs it here.

**循环反射弧(代替人肉审批)**:CI 绿 · golden-set 不回归 · 部署健康检查失败自动回滚 · 全程留痕。
**唯一人肉门**:以作者名义的对外发布。

---

## Cycle 0 — 2026-07-10 · 章程生效 / Charter ratified

- **决策**:品牌定为 **VidSnap — a glass-box AI video workbench**(透明 trace · 可审计 citations · 可复现 evals);内容严格双语;代码全自主发版,外发唯一门控。
- **动作**:合并 P0 硬化 PR [#5](https://github.com/PCcoding666/Vidsnap/pull/5)(声明对齐 Fun-ASR、彻底移除 Supabase、`visual_mode` 帧可选、CI 落地;48 tests、120 golden evals 通过)。
- **实测教训**:`fun-asr-flash` 是不存在的 model id——真实视频端到端测试当场翻车,探测 DashScope 后改回 `fun-asr`。教训:**声明必须被真实样例验证过才算数**。
- EN: Charter live. P0 hardening merged (#5). Real-video test caught a nonexistent ASR model id — claims only count after a real-sample run.

**下一 cycle(R1 开工)**:透镜 = 第一印象。README 重定位 + trace GIF + golden-set 成绩单徽章。

---

## Cycle 1 — 2026-07-10 · 第一印象 / First impressions

- **透镜**:陌生人打开 repo 的前 10 秒能否看懂"这个项目为什么不同"。
- **发版**:README 重定位为 glass-box 定位(双语 hero + 三支柱表);新增 **planner golden-set 公开成绩单徽章**——CI 每次 push 主分支自动重跑 120 条 eval(严格口径:required/forbidden/artifact_type/校验四条同时满足),发布到 `badges` 分支。
- **数据**:本地实测严格全条件通过 **120/120 (100%)**。敢公开成绩单,是因为成绩单是 CI 算的,不是自己说的。
- EN: Repositioned the README around the glass-box thesis and added a live planner-evals badge — CI re-scores all 120 golden cases (strict: required + forbidden + artifact type + validation) on every push. Current: 120/120.

**下一 cycle**:内容 #1 双语稿《AI 给我的项目做尽调,发现我的文档在撒谎》。
