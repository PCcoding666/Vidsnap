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

---

## Cycle 2 — 2026-07-10 · 内容 #1 双语稿 / First content piece

- **交付**:[中文稿](content/2026-07-ai-due-diligence.zh.md) + [英文稿](content/2026-07-ai-due-diligence.en.md)——《我让 AI 给自己的项目做尽调,它发现我的文档在撒谎》。素材 100% 来自真实尽调与修复记录(五条"声称 vs 实际"、根因诊断、fun-asr-flash 翻车实录),含可复用的尽调 prompt 骨架。
- **状态**:草稿,待作者审阅后发布(Ring 1:对外发布永远由作者执行)。
- EN: Drafted content #1 in both languages from the real audit-and-repair records; publishing stays human-gated.

**下一 cycle**:trace 演示截图/GIF(用真实浏览器抓 Workspace 的工具链执行画面,补进 README 首屏)。

---

## Cycle 3 — 2026-07-10 · 一镜实拍 / One real take

- **交付**:README 新增「一镜实拍」——真实运行截图(上传→规划→转录→索引→成稿,5 步 trace 全绿+产物面板);采集脚本落库 `scripts/capture_demo.mjs`(Playwright,发版即可复现)。
- **递归彩蛋**:demo 视频旁白介绍的就是 VidSnap,工具转录后在产物里亲手写下"Vid Snap 是一个'玻璃盒'(Glass Box) AI 视频工作台"——**工具处理了一条介绍自己的视频,并写出了自己的定位**。
- **过程曲折(glass-box 如实记录)**:两条浏览器遥控通道均被 macOS 权限挡下(扩展未连接、AppleScript -1743),遂改用 Playwright 无头采集——反而沉淀成可复现的 demo 采集基建。服务重启还暴露了 in-memory job 全丢(P1-1 持久化缺口再次被现实验证)。
- **新发现(自我挑战)**:执行中进度 85% 时 trace 各步仍显示"待执行"——**中途状态不实时**,已入队列。
- EN: Added a real, unstaged run screenshot to the README (captured via Playwright, script committed). The demo video narrates VidSnap itself — the tool wrote down its own positioning. Also caught a real UX gap: per-step trace states don't update mid-run.

**下一 cycle**:influence-metrics 采集器(GitHub stars/traffic 快照,为影响力周会供数)→ 之后:分享运行页、trace 中途状态实时化。
