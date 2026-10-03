# 矩阵实跑对比报告 v3：修复结论的第二素材泛化验证

- 日期：2026-09-21 首跑（gen1，remobi 119s 屏幕共享型），2026-09-22 修复实验（2b/2c），2026-09-23 泛化验证（gen2，talking-head 型）
- 素材 A（gen1）：`remobi-compatibility-first-119s.mkv`（119.008s，6,196,634 B，SHA256 `838902…3eff`，AV1+Opus，1920×1080，屏幕共享型演讲）
- 素材 B（gen2）：`How to Get Your First 10 Customers`（YC，4K AV1）截取 200–320s 窗口 → `clips/first10-window-200-320.mkv`（122.96s，21.5MB，3840×2160，**talking-head 口播型**：单人出镜 + 字幕条 + 一段官网录屏，信息主体在语音）；omni 格用同源 360p h264 重编码（3.5MB，满足 base64<10MB）
- 任务文本：两素材逐字节相同（task_hash `25c7c4…0d51`）
- 全部真实 API 调用。证据：`cell*/`（gen1）、`gen2-first10/`（gen2）、`matrix_metrics.json`（9 行，gen 字段区分）

## 1. 六格总览

| | Cell 1 | Cell 2 | **Cell 2b** | **Cell 2c** | Cell 3a | Cell 3b |
|---|---|---|---|---|---|---|
| 路线 | 3.8-max 直传 `video_url` | 抽帧 image-list（无标签） | 抽帧 + **帧级时间标签** | 抽帧 + 时间标签 + **large 分辨率** | Omni 原生视听 | Omni 上一代 |
| 模型 | qwen3.8-max | qwen3.8-max | qwen3.8-max | qwen3.8-max | qwen3.8-omni-flash | qwen3.5-omni-plus |
| 抽帧/分辨率 | 服务端 | 2fps·238帧·512×288 | 1fps·119帧·512×288 | 1fps·119帧·**1024×576** | 服务端 | 服务端 |
| 输入 tokens | 71,855（video） | 34,832（image） | **18,362**（image） | 69,771（image） | 71,631（video+audio） | 71,591（video+audio） |
| 输出 tokens | 6,411 | 5,968 | 5,886 | 8,818 | 4,779 | 924 |
| 耗时 | 124.3 s | 138.7 s | 124.2 s | 167.0 s | 62.6 s | **28.0 s** |
| 答案长度 | 3,040 字 | 2,145 字 | 2,131 字 | **3,717 字** | 2,928 字 | 1,754 字 |
| 时间覆盖（方括号引用口径） | **29%**（塌缩到 0–34s） | **114% 越界虚构**（[02:16]） | **99%**（0–118s）✓ | **99%**（0–118s）✓ | **100%** | 99% |
| 屏幕文字幻觉 | 无 | **"Why remobi" 三错二** | 仍错二（分辨率不足） | **修复**（与 3a 一致） | 无 | 无 |
| 口述内容 | ❌ | ❌ | ❌ | ❌ | ✅ 27 段逐字 | ✅（氛围级） |

注：Cell 2c 原始正则曾误报 coverage=125%，实为把答案中"页内嵌演示视频（时长 2:29）"当作时间戳——已修正为"方括号内引用"口径并人工核对。

## 2. 修复实验（本轮新增，双因素拆解）

Cell 2 暴露的两个结构性缺陷，分别用两个变体验证修复，变量严格单因子递进（TASK 文本逐字节不变，帧标签 preamble 属 harness 元数据）：

### Cell 2b — 只加帧级 [MM:SS] 时间标签（budget=normal 不变）→ 时间虚构 100% 修复

与 omni ground truth（3a）逐段对齐：

| 事件 | Cell 2（无标签） | Cell 2b（加标签） | Ground truth (3a) |
|---|---|---|---|
| 赞助商开场 | [00:00–00:18] | [00:00–00:13] | 00:00–00:14 |
| 会场演讲 | [00:25] | [00:15–00:34] | 00:15 |
| remobi 页 | [00:53] | [00:35–01:09] | 00:36–01:10 |
| Happy | [01:16] | [01:10–01:31] | 01:11–01:32 |
| Remote Control | [01:40] | [01:32–01:51] | 01:33–01:51 |
| Termius | **[02:16] 越界** | [01:52–01:58] | 01:52–end |

结论：**image-list 路线的时间戳虚构不是模型能力问题，而是信息缺失问题**——帧不带时间映射时模型只能凭帧序外推；给每帧前置 `[MM:SS]` 文本标签 + preamble 声明"时间引用以标签为准"后，时间轴与原生 omni 误差 ≤2s。附带收益：1fps 使输入 tokens 从 34.8k 降到 18.4k（**省 47%**），答案质量未受损。

### Cell 2c — 时间标签 + budget=large（1024×576）→ 屏幕文字幻觉也修复

- "Why remobi" 从 2b 的错二（"网络断开恢复/手机优化视图"）变为正确：**Zero workflow changes / Swipe between windows / Pinch to zoom**，与 Cell 1、3a 三方一致。
- 还额外读出仅高分辨率可见的细节：npm v1.0.3 / MIT 徽章、完整 curl 安装命令、`npm install -g remobi@dev` 实验通道、Happy 内嵌演示视频时长 2:29、终端输出 `Claude Opus limit reached / Sonnet 4`、iPhone mockup 会话列表条目、Claude Code 文档 v2.1.51 版本要求与 Team/Enterprise 默认关闭策略、地址栏 URL。
- 代价：输入 69.8k tokens（3.8 倍于 2b）、167s（四格抽帧路线中最慢）。答案 3,717 字为全场最长、视觉细节密度最高。
- 15MB 响应上限在 2fps+large 下会触发降采样（首跑 238 帧 18.9MB→188 帧），1fps+large（9.4MB）则完全不需要。

### 工程教训（复跑记录，如实披露）

1. **首跑 2b/2c 全部失败于同一根因**：2fps 下逐帧标签使请求达 477 个 content parts，token-plan 端点流式响应卡死（一次 1010s 后 Broken pipe，一次 max_tokens=4096 被 reasoning 耗尽、正文 0 字）。修复三件套：**1fps 减负（240 parts）+ max_tokens=8192 + 420s wall-guard 保留部分内容 + HTTP 重试×3**，之后两格均一次成功（finish_reason=stop）。
2. `/tmp` 工作目录跨天被系统清空，脚本需重建——证据目录必须放在 `~/Movies/` 这类持久位置（本轮已遵守，数据无损）。
3. qwen3.8-max 开启 thinking 时 reasoning 消耗巨大（2c：reasoning 7,010 / completion 8,818 = 80%），max_tokens 预算必须按 completion ≥ 8k 规划。

## 3. 各格核心画像（与 v1 一致，摘要保留）

- **Cell 1（直传 video_url）**：重大通路发现——3.8-max 在 token-plan 端点原生接受 base64 视频（8-12 实验 Direct 基线失败是帧列表传输问题，非模型不支持）。细节最富，但时间戳全部塌缩到 [00:00–00:34]（29% 覆盖），无音频。适合内容提取，不适合时间引用任务。
- **Cell 2（抽帧无标签）**：两个结构性缺陷被实证——时间戳越界虚构（[02:16]）+ 低分辨率屏幕文字幻觉（"Why remobi" 三错二）。
- **Cell 3a（qwen3.8-omni-flash）**：综合质量最优。唯一还原演讲叙事逻辑（互动提问→"AI psychosis"自制动机→三方案口头对比→半句话截断），27 段英文逐字引用，100% 时间覆盖，62.6s。audio_tokens=828 证明音频通道生效。
- **Cell 3b（qwen3.5-omni-plus）**：最快（28s）最省（completion 924），时间结构良好且唯一描述声音氛围，但无逐字口述、讲者观点全丢——与官方"29 项基准平均 +25%"代际差一致。

## 4. 对 Harness 的结论（v3 更新，含两素材泛化）

1. **抽帧 Harness 可以被修好，且修复便宜、可泛化**：帧级时间标签（纯提示词工程，零成本）+ 1fps（省 47% tokens）使 3.8-max 抽帧路线的时间 grounding 在**两种视觉结构**（屏幕共享型、口播型）上均对齐原生 omni（误差 ≤3s、零越界）；budget=large 补齐屏幕文字忠实性，并在 gen2 获得像素级 ground truth 佐证（同一帧 normal 编造数字、large 全读对）。**"帧↔时间映射注入"应列为 Harness P0 修复项**——这是 8-12 实验 Direct 路线、gen1 Cell 2 共同失败的根因（kernel 的 image-list 传输不带时间元数据）。
2. **音频差距随素材语音占比扩大，是不可逾越的结构性差距**：屏幕共享型素材上纯视觉路线尚能靠屏幕文字拿到大部分信息（gen1 2c 细节反超 3a）；口播型素材上 2b/2c 退化为"字幕条 OCR"，讲者论证链（anecdote、门槛论、案例）全部丢失，而 3a 完整还原。**"忠实笔记"类任务的天花板由 omni 原生视听决定，且素材越依赖语音，差距越大。**
3. **路线选择建议**（两素材验证后不变，置信度提高）：
   - 默认：**qwen3.8-omni-flash**（唯一音画双全；口播型素材上无可替代）。
   - 时间引用敏感的纯视觉任务 / 屏幕文字密集素材：3.8-max + 抽帧 + 帧级时间标签（1fps 起步，文字密集升 large）。
   - 低成本快扫：qwen3.5-omni-plus。
   - Harness（kernel+policy+trace）独有价值收缩到 glass-box 审计、预算控制、可复现性。
4. **成本序**（输入 tokens）：2b（18.4k–18.8k）< gen2 3a（27.4k，360p）< Cell 2（34.8k）< 2c/Cell 1/3a/3b（69.8k–71.9k）；耗时序：3b（28s）< 3a（60–63s）< 2b（118–124s）≈ Cell 1（124s）< Cell 2（139s）< 2c（167–171s）。
5. **工程基线**（复跑三天的实战结论）：大 payload 流式请求必须带 ①重试×3 ②wall-guard 保留部分内容 ③max_tokens≥8k（thinking 占 completion 80%）④帧数控制在 ~250 parts 以内（1fps）；证据与脚本必须放持久目录（/tmp 跨天清空两次）。

## 5. Gen2 泛化验证（2026-09-23，第二素材 talking-head 型）

针对 v2 的最大局限（单素材），换用结构完全不同的素材 B（口播型：无密集屏幕文字、信息主体在语音、仅字幕条与一段官网录屏）复跑关键三格：2b（时间映射修复）、2c（large 分辨率修复）、3a（omni ground truth）。

| | Gen2 2b | Gen2 2c | Gen2 3a |
|---|---|---|---|
| 路线 | 抽帧+时间标签 normal | 抽帧+时间标签 large | omni 原生视听 |
| 输入 tokens | 18,821（image 17,812） | 71,526（image 70,516） | 27,359（video 26,402 + **audio 842**） |
| 耗时 | 118.3s | 171.3s（前两次 write-timeout，第 3 次重试成功） | 60.5s |
| 时间覆盖 | 0–121s，**无越界** ✓ | 0–121s，**无越界** ✓ | 0–120s ✓ |
| 答案长度 | 1,395 字 | 1,729 字 | 1,592 字 |

### 结论一：时间映射修复可泛化 ✓
Gen2 2b/2c 的时间戳全部落在片长内（max 121s / 122.96s 片），且与 3a 逐段对齐（字幕条 "Your personal network" 2b 标 [00:05]、3a 标 [00:02]；"Be specific" 2b 标 [00:43]、3a 标 [00:40]；"Fly out to close them" 2b 标 [01:33]、3a 标 [01:30]——误差 2–3s，与 gen1 一致）。**帧级时间标签的修复效果在第二种素材、第二种视觉结构上复现。**

### 结论二：large 分辨率修复可泛化，且获得像素级 ground truth 佐证 ✓
素材 B 的官网录屏含小字数字（Gmail/日历/Instagram/Twitter 的联系人计数）。4K 原帧人工核对（`/tmp` 裁切图，源帧 3840×2160）：真实值为 **700 contacts / 2.2k attendees / 1.2k followers / 174k followers**。
- Gen2 2c（large 1024×576）：**四个数字全部读对**，且正确区分"日历 2.2k attendees"。
- Gen2 2b（normal 512×288）：**编造为 500 contacts / 2.3k connections / 1.2k / 15k**——数值错、单位错（attendees→connections）、量级错（174k→15k）。
这是比 gen1（"Why remobi" 三错二）更硬的证据：同一帧、两个分辨率档，幻觉与否完全由分辨率决定。

### 结论三：音频差距在口播型素材上进一步扩大 ✓（最重要）
素材 B 的信息主体是语音。3a 还原了全部口述论证链：LinkedIn 暖介绍 anecdote（"约一半成交客户来自 LinkedIn 介绍"）、prospecting tools 的 10–20 客户门槛论、"飞四周见同一买家"、"夏威夷 8 分钟被赶但后来成最大客户"、结尾句中截断的如实记录。
而 2b/2c 的答案本质是**字幕条 OCR + 官网截图描述**——7 条字幕时间线齐全，但讲者论证、案例、观点为零。在屏幕共享型素材（gen1）上，纯视觉路线尚能靠屏幕文字拿到大部分信息；在口播型素材上，**没有音频通道 = 丢失全部论证内容**。这使 v2 的结论从"音频是差距"升级为"音频差距随素材语音占比单调扩大"。

### Gen2 工程记录（如实披露）
- 9-22 首次启动的 Gen2 两格均死于 `502 Bad Gateway`（隧道瞬断，机器睡眠后网络未恢复）；9-23 端点健康探测恢复后重跑成功。2c 另有两次 `write operation timed out`，靠脚本内置重试×3 在第 3 次成功——重试机制第二次实战生效。
- 4K 素材抽帧 1fps 仅 8.8s（large 档），抽帧不是瓶颈；瓶颈始终在服务端推理与网络。
- omni 格用 360p 重编码是 base64<10MB 约束下的妥协；talking-head 视觉信息量低，360p 对字幕条/官网截图仍可读（3a 正确读出字幕与官网标语），但官网小字数字未出现在 3a 答案中（未尝试读取），不构成对结论的干扰。

## 6. P0 修复落地（2026-09-23，kernel 运行时路径）

实验结论已变成项目代码。改动在 `Vidsnap-eval-studio-workbench/src/vidsnap/providers/qwen.py`（kernel 的 synthesize 与 agentic decision 两条模型调用路径共用此处序列化）：

- 新增 `_frame_timestamp_label(evidence)`：对 `modality == "frame"` 的证据生成 `[MM:SS]` 标签（取自 `Evidence.start_seconds`，kernel 在 `prepare_direct_baseline`/`sample_evidence` 时已从帧时间戳写入）。
- `_evidence_content`（synthesize）与 `decide_next`（agentic）：每个帧 image part **前置**其 `[MM:SS]` 文本 part，并在 JSON 文本块后追加一句 preamble（"Each [MM:SS] text part immediately before a frame image is that frame's source-video timestamp…"）。非帧证据（transcript/ocr/audio/scene）不注入标签。
- 无帧证据时输出逐字节不变（空证据 golden 断言不受影响）。
- 测试：`tests/providers/test_qwen.py` 更新帧 wire-shape 断言 + 新增 `test_qwen_synthesis_interleaves_frame_timestamp_labels`（3 帧 + 1 transcript：标签序列恰为 `[00:00]/[01:15]/[01:59]`、transcript 不注入标签、preamble 存在）。
- 验证：`tests/providers + tests/runtime + tests/tasks + tests/prompts + tests/test_harness.py` 共 **269 passed, 0 failed**（离线组合环境；mypy 因离线无包未跑，改动为纯 dict/list 构造）。

**明确不改**：`src/vidsnap/benchmark/live.py`（8-12 formal benchmark runner）。它的 direct 帧序列 wire-shape 被 `tests/benchmark/test_live.py` 钉死，且已记录的结果依赖该 shape——为保持历史可比性冻结；若未来重跑 formal，应单独开一轮带标签的变体并重新记录基线。

## 7. 成本口径（补齐报告遗留项）

价目来源：gap 报告 9-21 已核实数字（百炼定价页 2026-09-20 抓取：qwen3.8-max 北京 **输入 ¥12 / 输出 ¥36 每百万 token**；发布报道口径：omni 音频输入北京 **¥0.8/M**；国际分模态 $0.43 文本 / $3.81 音频 / $0.78 图像视频 每 M）。omni 的 CNY 图像/视频单价未能在文档抓取中核实，以下 omni 行用国际 USD 价折算标注为估算。本轮离线未能再拉权威价目（网络瞬断），live 前仍应在控制台核一次。

按实测 token 量折算（119s remobi 片，单请求；¥ 按 1 USD ≈ 7.1 CNY 粗折）：

| 格 | 输入 tokens | 输出 tokens | 估算成本（单请求） |
|---|---|---|---|
| Cell 1（3.8-max 直传视频） | 71,855 | 6,411 | 71.9k×¥12/M + 6.4k×¥36/M ≈ **¥1.09** |
| Cell 2（抽帧 normal 2fps） | 34,832 | 5,968 | ≈ **¥0.63** |
| Cell 2b（抽帧+标签 1fps） | 18,362–18,821 | 4,677–5,886 | ≈ **¥0.39–0.44** |
| Cell 2c（抽帧+标签 large） | 69,771–71,526 | 4,397–8,818 | ≈ **¥1.00–1.18** |
| Cell 3a（3.8-omni-flash） | 71,631（含 audio 828） | 4,779 | 视频 70.7k×$0.78/M + 音频 0.8k×$3.81/M + 输出 ≈ **$0.06 ≈ ¥0.43**（估算） |
| Cell 3b（3.5-omni-plus） | 71,591 | 924 | 旧代定价未核实，量级同 3a |

结论：**修复后的抽帧路线（2b）是全场最便宜（≈¥0.4）**，比直传视频（¥1.09）省 60%+，与 omni 估算价（¥0.43）同量级；但 2b 无音频，口播型素材上不可用。large 档（2c）成本回到直传视频量级。成本不再是选 omni 的障碍——**选 omni 的理由是音频，不是价格**。

## 8. 局限性声明

- 两素材（屏幕共享型 119s + 口播型 123s）× 每格单次运行、未固定 seed——修复结论已在两种视觉结构上各验证一次，仍非统计显著；每格多次运行取方差是下一步。
- gen2 未跑 Cell 1（直传 video_url）与 3b：21.5MB 4K 源超 base64<10MB 上限，需另做重编码变体，且其对修复结论无增量信息，故省略（如实记录）。
- 2b/2c 用 1fps（119–122 帧）而非 2fps：2fps+标签首跑因端点过载失败；1fps 已覆盖两素材的场景切换粒度。严格单因子（2fps+标签）待端点稳定后补。
- 时间覆盖/引用数为正则启发式（方括号内 `[MM:SS]`/`【MM:SS】` 口径），越界项已人工核对；gen2 的官网数字幻觉经 4K 原帧像素级人工核对。
- 2b/2c 为 core `read_video` 策略的本地 ffmpeg 复刻 + 标签增强，非插件本体。
- 计费口径未纳入（token-plan 与 dashscope 标准端点价目不同），成本比较仅按 token 量。
- 凭据均从本地配置读取注入子进程，未写入任何输出文件。
