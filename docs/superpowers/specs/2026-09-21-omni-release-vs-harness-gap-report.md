# Qwen3.8-Omni 发布 × Vidsnap Harness 差距对比报告

- **日期**：2026-09-21（Asia/Shanghai）
- **性质**：调研 + 对比分析报告（只读产物，不含代码改动；符合"Qoder 只写代码、lead 只写文档/评审"的工作约定）
- **关联任务**：`docs/superpowers/plans/2026-09-12-native-video-comparison.md`（两路对比实验，Batch 2 进行中、live 未跑）
- **调研来源**：百炼官方文档（模型页/定价页/Qwen-Omni 页）、Qwen 官方博客发布公告（2026-09-18）、Qwen-MM-Plugins Hub 与 GitHub 仓库、第三方定价分析（aireiter）、知乎/新浪发布报道

---

## 0. TL;DR（最重要的 5 个结论）

1. **你 9-12 计划里钉死的 native 路线模型 `qwen3.5-omni-plus` 已经过时了。** 2026-09-18（计划定稿 6 天后）百炼上线了 **Qwen3.8-Omni-Flash** 和 **Qwen3.8-Omni-Flash-Realtime** 两个新 SKU：29 项评测平均比 qwen3.5-omni-plus 高 25%+，Agent 基准 WildClawBench-MM 从 34.5 → 71.0，多说话人会议转写 DER 从 88.1 → 3.4（从不可用到可用），音频输入降价 98%、音视频输入降价 93%。**继续用 3.5-omni-plus 跑对比，等于用一个已被官方全面超越的旧模型代表"native 路线"，结论会系统性低估 native 侧。**
2. **官方同时开源了 Qwen-MM-Plugins（13 个插件）+ Qwen-Live Harness**，其中 `core`（本地抽帧/媒体元数据）、`api`（omni_asr_timestamped、omni_multi_speaker_asr、omni_av_caption、omni_av_grounding 等 13 个工具）、`video-memory`（长视频 4 级层次图记忆）、`omni-video2note`（教程视频→图文 PDF）与 Vidsnap Harness 自研的 `sample_evidence` / `transcribe_audio` / interview recipe 高度重叠。**Vidsnap 的"给 agent 装视频工具"价值主张被官方工具链部分覆盖，护城河必须收缩到 glass-box 审计、可复现 eval、预算与证据真实性上。**
3. **能力差距（native 3.8 omni vs 当前 Harness）**：原生模型单次请求可吃 2 小时连续音视频（2GB URL / 10MB base64）、15fps 高动态采样、自带音轨理解与说话人分离、1M 上下文、默认深度思考（reasoning_effort=xhigh）且支持 Function Calling；Harness 路线是 24 帧上限 + 最多 3 个时间窗 + 本地 Whisper 转录 + ≤3 轮迭代/≤12 次模型调用的有界循环。**信息覆盖率上 native 是"全片连续"，Harness 是"稀疏采样"，这是结构性差距，不是调参能补的。**
4. **Harness 仍然领先的维度**：证据可审计（RunBundle/trace 导出/请求字节计量/usage 不造假）、确定性预算与 fail-fast、隐私脱敏（不落原始响应/密钥/CoT）、golden-set 可复现成绩单（120/120）、零密钥离线 demo。官方插件（如 omni-video2note）内部是黑盒 bounded workflow，只返回 `api_calls/timings` 汇总，没有可检查的事件级证据链。**"glass-box"仍是差异化，但要更快把 Batch 2 的 P1 修完、跑出真实对比数据来证明它。**
5. **恢复实验的第一步不是写代码，是重新批准实验设计**：把 native 路线的模型 pin 从 `qwen3.5-omni-plus` 换成（或增加）`qwen3.8-omni-flash`；显式设置并如实记录 `reasoning_effort`；usage 记录扩展到新模型的分模态 token 明细（audio_tokens/video）；顺带评估把 `omni-video2note` 作为"官方现成基线（route 0）"加入对比。119s/6.2MB 测试片在新模型下仍然满足 base64 ≤10MB 约束，且新模型 2 小时/2GB URL 上限意味着 **Batch 3 的"全片分块计划"可能整个不再需要**——remobi 全片或许单次请求就能覆盖。

---

## 1. 百炼上最近的 Qwen3.8 Omni 系列发布

### 1.1 发布清单（2026-09-18 一次发布两个 SKU，另有周边一个）

| 模型 | 发布/上线 | 定位 | 状态 |
|---|---|---|---|
| **qwen3.8-omni-flash** | 2026-09-18 | 新一代原生全模态（文/图/音/视频入，文本出），主打音视频理解 + Agent 交付 | 已上线百炼 |
| **qwen3.8-omni-flash-realtime** | 2026-09-18 | 超低延迟实时版，边收音视频流边响应，支持 WebSocket/WebRTC，"听声辨位"（空间音频定位） | 已上线 |
| Qwen3.8-LiveTranslate | 2026-09-19 | 同声传译专用模型（Interleave 架构，非传统 ASR→MT→TTS 流水线），omni 家族周边 | 已发布 |

### 1.2 qwen3.8-omni-flash 关键规格（百炼官方模型页，更新于 2026-09-17/18）

- **地域**：华北2（北京）、新加坡、中国香港、东京、法兰克福、弗吉尼亚（需对应地域 API Key）
- **上下文**：1M token（非思考模式最大输入 991,808；思考模式 983,616；最大输出 131,072）
- **模态**：输入 文本+图片+音频+视频（可同一请求混合）；输出 仅文本
- **能力**：Function Calling ✅、联网搜索 ✅（Responses 内置 `web_search`）、深度思考默认开启（`reasoning_effort` 默认 `xhigh`，可选 none/minimal/low/medium/high/xhigh/max）、隐式上下文缓存自动生效、多通道音频（立体声 + 4 声道 FOA 空间音频，`use_multichannel`）
- **思考保留**：`preserve_thinking` 默认开启（历史 thinking 计入输入 token 与费用——做成本核算时必须注意）
- **音频语种**：输入 113 种语言/方言（与 Qwen3.5-Omni 一致）

### 1.3 输入限制（对比实验最相关的硬约束）

| 项 | qwen3.8-omni-flash | qwen3.5-omni 系列（旧 pin） | qwen3-omni-flash |
|---|---|---|---|
| 视频时长 | **2 小时**（官方公告口径：最长 1 小时完整连续音视频输入；文档时长上限 2h） | 1 小时 | 150 秒 |
| 视频文件（公网 URL） | **2 GB** | 2 GB | 256 MB |
| 视频文件（Base64 内联） | **< 10 MB**（编码后） | < 10 MB | < 10 MB |
| 单次请求视频文件数 | 64 | URL 512 / Base64 250 | 1 |
| 音频时长 | 3 小时 | 3 小时 | 20 分钟 |
| 图像序列（视频当帧序列喂） | 2–2048 张 | 2–2048 张 | 2–128 张 |
| 帧率 | 高动态描述模式最高 **15 fps** 稳定；帧率越高成本越高 | — | — |
| 流式 | 文档示例 stream=True（3.5 系列强制） | 强制 stream=True | 强制 |

> ⚠️ 对实验的含义：6.2MB 的 119s AV1/Opus MKV 片段 base64 后约 8.3MB，仍贴近 10MB 上限（这是 9-12 计划里 `MAX_INLINE_BASE64_BYTES = 10_000_000` 校验存在的原因，对新模型同样适用）。但**全片扩展不再必须分块**：remobi 全片若 <2GB 且 <2h，可走公网 URL 单请求。

### 1.4 基准成绩（官方博客 vs qwen3.5-omni-plus，实验设计直接相关项加粗）

| 基准 | 类别 | qwen3.8-omni-flash | qwen3.5-omni-plus |
|---|---|---|---|
| **WildClawBench-MM** | 多模态工具使用/Agent | **71.0** | 34.5 |
| **AgenticVBench** | 多模态工具使用/Agent | **36.8** | 14.5 |
| UniClawBench | 多模态工具使用 | 69.6 | 67.1 |
| **OmniVideoBench** | 音视频推理 | **63.4**（agentic 模式下 67.8） | 53.8 |
| **LVOmniBench** | 长视频推理 | **63.3** | 53.2 |
| Video-MME-v2 | 音视频推理 | **65.0** | 47.9 |
| DailyOmni | 音视频理解 | 85.1 | 85.1 |
| AVUT | 音视频理解 | 86.6 | 85.9 |
| StreamingBench | 音视频交互 | **80.8** | 57.1 |
| LongAudioSpan | 长音频推理 | **82.7** | 74.4 |
| **AliMeeting（DER/cpWER，多说话人会议）** | 说话人分离+转写 | **3.4 / 17.2** | 88.1 / 89.6 |
| AISHELL-4（DER/cpWER） | 同上 | **2.8 / 11.2** | 100.0 / 100.0 |
| WenetSpeech Net（WER） | 单人 ASR | 4.8 | **3.7** |
| SWE-bench Pro / AndroidWorld / LVBench | 文本&视觉 Agent | 63.3 / 87.1 / 76.9 | — |

要点：
- 官方称音视频能力**接近 Gemini 3.8 Flash，纯音频能力超过之**。
- **多说话人场景从"完全不可用"变成"可用"**——这直接冲击实验里"native 有音轨、Harness 靠本地 Whisper"的混淆变量声明：新 omni 的转写+分离质量可能远超本地 Whisper，混淆变量的方向对 native 更有利，报告里必须更新表述。
- Agentic 长视频理解自带 coarse-to-fine 证据收集：OmniVideoBench 上准确率 63.4→67.8 的同时 token 消耗 145,736→79,117（-45.7%）——**官方模型内置了"少花钱多取证"的策略，这正是 Harness 用预算循环外置实现的东西**。

### 1.5 定价（已核实的数字）

**北京地域（CNY，每百万 token）**：
- 音频输入：**¥0.8**（上一代 ¥18，降幅 >98%）——来源：知乎发布解读引用官方数据
- 音视频输入整体：降幅 >93%（官方公告口径；每小时价格 = 2 分钟源材料输入成本 × 30 估算，音视频按 720p@1fps）
- qwen3.8-omni-flash 的分模态 CNY 完整价目表官方文档页未在抓取内容中展开，**上线前需在百炼控制台按北京地域核实**
- 参照：Harness 用的 **qwen3.8-max（北京）= 输入 ¥12 / 输出 ¥36**（每百万 token，Batch 调用半价、缓存有折扣、100 万 token 免费额度）

**新加坡/国际地域（USD，每百万 token，aireiter 引官方价目表）**：

| 计费项 | 单价 |
|---|---|
| 文本输入 | $0.43 |
| 音频输入 | $3.81（≈文本的 8.9 倍） |
| 图像/视频输入 | $0.78 |
| 文本输出（纯文本输入后） | $1.66 |
| 文本输出（多模态输入后） | **$3.06**（多模态输入会把输出单价抬高 84%） |

**119s 测试片的量级估算**（⚠️ 估算，假设 720p@1fps≈119 帧、每帧≈1,100–1,600 token，音频≈25 token/秒；官方未公布精确 token 换算公式）：
- **native 路线（qwen3.8-omni-flash，单请求）**：视频 ~13–19 万 token + 音频 ~3 千 token → 国际价约 **$0.10–0.15**，北京价按 93% 降幅推算约 **¥0.5–1**。
- **Harness 路线（qwen3.8-max，≤6 次调用）**：每次调用携带 ≤24 帧图 + 转录文本 + schema，单次输入 ~3–4 万 token → 全跑下来约 **¥1.5–3**（Token Plan 端点计费可能不同，需按实际账单口径）。
- 结论：**native 单请求在成本上已经打平甚至低于 Harness 多轮循环，且信息覆盖率是全片 vs 稀疏采样**。9-12 计划里"native 更贵所以只跑一次"的隐含假设需要复核。

---

## 2. Qwen-MM-Plugins 工具链全景（与 Vidsnap 组件的映射）

**仓库**：github.com/QwenLM/Qwen-MM-Plugins（Apache-2.0，活跃开发，9-20 仍有更新）；Hub：qwenlm.github.io/qwen-mm-plugins-hub/
**架构**：每个能力 = Skill（行为指令）+ 可选 MCP server（工具），独立不可变 tag 版本化；共享配置 `~/.qwen-mm-plugins/config`
**支持的 harness**：Claude Code、CodeBuddy、Codex、Qoder、OpenClaw、Qwen Code、Gemini CLI（引导安装）；WorkBuddy/QoderWork/QwenWork（应用内）；DeepSeek Harness、Hermes Agent、opencode 等（手动）

### 2.1 与 Vidsnap 直接重叠的插件

| 插件 | 能力 | 对应 Vidsnap 组件 | 重叠度 |
|---|---|---|---|
| **core**（7 工具，无需 API key） | `media_info`（元数据）、`read_video`（抽帧）、`read_image`、`save_view`、`crop`、`draw_bbox`、`visualize`（PDF/Office/3D/NIfTI…） | `MediaProbe` + `sample_evidence` 插件 | **高**——本地抽帧/探测几乎同构 |
| **api**（13 工具，DashScope） | VL 组：`vision_chat`/`ocr`/`grounding`；Omni 组：`perceive_media`（通用音视频问答）、`omni_asr`、`omni_asr_timestamped`（句/词级时间戳+SRT）、`omni_multi_speaker_asr`（说话人分离）、`omni_av_caption`（时间轴 Markdown 描述）、`omni_av_grounding`（自然语言→时间段定位）、`omni_av_counting`（事件计数）、`omni_music_caption`；其他：`transcribe_audio`（Qwen3-ASR）、`segmentation`（SAM3） | `transcribe_audio` 插件（本地 Whisper/Fun-ASR）+ Harness 的证据获取 | **高**——且 `omni_asr_timestamped`/`omni_multi_speaker_asr` 提供本地 Whisper 没有的时间戳与说话人标签 |
| **video-memory**（9 工具） | 长视频（>30min）4 级层次图记忆：Root→SuperEvent→MacroEvent→Subgraph（实体/事件/OCR/关系边），先建记忆再查询，定位后用 `read_video` 窄窗口精查 | Vidsnap **没有对应物**（planner 只在全片上做窗口规划） | 能力空白——长视频正是 Batch 3 全片扩展要面对的 |
| **omni-memory** | 音视频记忆：谁在场、谁说了什么、语气、环境声 | 无对应物 | 空白 |
| **omni-video2note**（1 工具） | 教程视频→图文 PDF：Omni 分块理解→同一模型出笔记+步骤时间戳→本地按时间戳截图→渲染可搜索 PDF；`time_budget_seconds` 默认 150s、瞬态失败最多重试 1 次、失败降级用已有证据出简版、全失败返回结构化失败不编造 | **interview recipe**（`vidsnap recipe interview`：转录→成稿→brief→trace.html，验证通过才出产物） | **中高**——目标产物类似，但 Vidsnap 有验证门与 trace 审计，video2note 没有 |
| **omni-skill-creator** | 演示视频（可含口述理由）→可复用 Agent Skill | 无对应物 | 空白（有趣的产品参考） |
| omni-chatcut / video-edit / edu-agent / blender / freecad / search / mhs | MV 制作、影视解说、保说话人翻译、剪辑、教学视频、3D、网页/以图搜图、硬件 | 无对应物 | 不相关 |

### 2.2 Qwen-Live Harness

围绕 qwen3.8-omni-flash-realtime 的开源 harness（`npm install -g qwen-live-harness`）：悬浮球交互、任务委托+看板跟进+完成播报、长期记忆、上下文管理。Realtime API 首音频包 ~981ms（20s 音频输入）、原生支持最长 1 小时连续音视频流。
**含义**：官方把"实时音视频 agent 外壳"也做成了开源标件。Vidsnap 的非实时、强审计定位与之不冲突，但"做一个视频 agent harness"本身不再稀缺。

### 2.3 对 Vidsnap 的战略含义

- **被覆盖的**：本地抽帧、媒体探测、ASR（含时间戳/说话人）、视频→笔记、长视频记忆。这些自研组件的"功能价值"被官方免费/低价替代。
- **没被覆盖的（Vidsnap 护城河候选）**：
  1. **证据真实性与可审计**：RunBundle 事件级 trace、请求字节计量、usage 缺失≠0、失败分类不落原始载荷——官方插件只给汇总统计；
  2. **确定性预算与 fail-fast**：LoopBudgets（≤3 迭代/≤12 模型调用/≤6 工具调用/≤96 帧/≤900s）+ verifier + 修复轮，官方 bounded workflow 是黑盒内建；
  3. **可复现公开成绩单**：golden-set 120/120 CI 徽章；
  4. **零密钥离线 demo / 隐私脱敏**（call_review  sanitize 链路）。
- **建议叙事调整**：从"给 agent 装上视频能力"（官方已做）转向"**任何视频 agent（包括官方插件驱动的）都需要可审计的运行证据——Vidsnap 是 glass-box 运行与评测层**"。甚至可以考虑把 Qwen-MM-Plugins 的工具作为 Vidsnap registry 里的受控插件接入，让 Harness 的预算/审计包住官方工具。

---

## 3. 上一个对比任务（2026-09-12 计划）现状回放

**目标**：同一条 119s/6.2MB AV1/Opus MKV 片段，两路产出中文忠实笔记对比——
- **Route A（native）**：`qwen3.5-omni-plus` @ 北京 DashScope compatible-mode，单请求、stream=True、include_usage、base64 内联 ≤10MB、失败即停不重试；
- **Route B（Harness）**：qwen3.8-max @ Token Plan 端点 + 本地缓存 Whisper（TranscriptionPort）+ 注册工具 `transcribe_audio`/`sample_evidence`，预算 ≤6 次远程调用/≤4 次工具调用/≤24 帧。

**进度**：
- Batch 1 ✅：`providers/native_video.py`（307 行）、`providers/local_whisper.py`（244 行）+ 51 个聚焦测试通过、mypy 79 文件通过；
- Batch 2 ⏳：`scripts/native_video_review.py`（1101 行）已成型（validate-only + live 双模式、RunBundle、HTML/MD 评审报告），但 **9-12 两轮只读评审判定 NO-GO**，未修完；
- Batch 3 ⬜：live 对比未跑；
- 计划清单勾选状态：4 项完成 / 13 项未完成。

**挡在 live 之前的评审遗留（截至 9-12，均需 Qoder 修复）**：

| # | 级别 | 问题 | 位置 |
|---|---|---|---|
| 1 | P1 | Harness 侧仍用默认 `AgenticPolicy`：格式错误自动再请求、verifier 拒绝可触发修复——违反"失败即停、无重试"；且配置记录 `max_iterations=1` 与生效策略默认 3 不一致 | `scripts/native_video_review.py`（AgenticPolicy 装配处）+ `runtime/policies.py:127-163` |
| 2 | P1 | 24 帧上限在抽帧+落盘**之后**才检查（kernel 先执行插件后校验），`max_frames=25` 能通过参数校验 | `runtime/kernel.py:260` + `plugins/builtin/sample_evidence.py:53` |
| 3 | P1 | native 流非预期形状（如 `{"choices":1}`）抛未归类 TypeError，runner 只 catch `NativeVideoError`，绕过终态记录与 checkpoint；已收到的 usage（如 7/3）在流失败时丢失 | `providers/native_video.py:204,238` + `scripts/native_video_review.py:503` |
| 4 | P1 | ASR 执行事实（进程启动确认、退出码、模型身份）只在内存列表；Harness trace 导出失败时整段被替换为 failure class，实测事实丢失 | `scripts/native_video_review.py:680,703` |
| 5 | P2 | qwen.py 把任何非空 usage 当"完整上报"：只有 `prompt_tokens=7` 时产出 `output_tokens=0, reported=True`——缺失被伪造成 0 | `providers/qwen.py:347` + runner 聚合 `:379` |
| 6 | P2 | `call_review.py` 脱敏对嵌入式路径只认"行首或前导空格"：`(/tmp/private.mp4)`、`see(file:///...)`、双反斜杠 Windows 路径均存活 | `runtime/call_review.py:114-129`（9-7 评审遗留） |

---

## 4. 核心对比：qwen3.8-omni-flash（native）vs 当前 Vidsnap Harness

> Harness 侧按仓库现状描述：qwen3.8-max（Token Plan 北京端点）+ 本地 Whisper + 有界工具循环 + RunBundle/trace 审计。native 侧按百炼文档与官方公告描述。

| 维度 | qwen3.8-omni-flash（native 单请求） | Vidsnap Harness（qwen3.8-max + 本地 Whisper） | 差距方向 |
|---|---|---|---|
| **信息覆盖** | 全片连续音视频，2h/2GB（URL），15fps 高动态 | ≤24 帧 + ≤3 时间窗转录（实验口径），采样稀疏 | **native 大幅领先**（结构性） |
| **音频理解** | 原生：语音+音效+音乐+空间音频；113 语种；说话人分离 DER 3.4（AliMeeting） | 本地 Whisper 只出纯文本转录，无说话人/音效/音乐 | **native 大幅领先** |
| **时间定位** | 原生时间轴感知；`omni_av_grounding` 类能力可自然语言→时间段 | 证据带 [mm:ss] 锚定（Cycle 5 修复），依赖转录质量 | native 领先 |
| **推理/Agent** | 深度思考默认开（xhigh 可调）；Function Calling；官方 agentic 模式省 45.7% token | 模型只做严格 JSON 决策（tool_calls/final），无 thinking 落盘，planner+agent 双角色 | 能力上 native 领先；**可控性上 Harness 领先**（模型不能改预算/端点/工具） |
| **成本（119s 片）** | 估算 ¥0.5–1（北京，单请求） | 估算 ¥1.5–3（≤6 次 max 调用；Token Plan 计费另算） | native 持平或更低（新定价后） |
| **延迟** | 单请求，但视频编码上传 + 思考模式可能长尾 | 多轮串行（转录→采样→合成→验证→修复），墙钟更长（预算 900s 上限） | native 大概率更快 |
| **证据可审计** | 只有请求/响应与 usage 汇总；内部帧采样不可见（官方口径：provider 内部处理"unknown，不重建"） | RunBundle 事件级 trace、工具参数/结果记录、模型请求前证据快照、请求字节计量、HTML trace 导出 | **Harness 大幅领先**（glass-box 核心卖点） |
| **usage 真实性** | usage 含分模态明细（audio_tokens 等），但缺失语义需自行保守处理 | 显式设计：缺失≠0、未上报不伪造（P2 #5 修完后成立） | Harness 领先（前提：把 #5 修掉） |
| **隐私** | 原始响应含完整模型输出；需自建脱敏 | call_review 脱敏链路（P2 #6 修完后达标）；子进程环境清洗（Whisper 无凭证） | Harness 领先（有已知缺口待修） |
| **可复现/回归** | 无内置评测面 | golden-set 120/120 CI 徽章、conformance、可复现 eval 套件 | **Harness 独有** |
| **失败语义** | 单点：失败即无产物（实验设定 fail-stop） | 终态机（SUCCEEDED/PARTIAL/FAILED/EXHAUSTED/BLOCKED）+ 失败分类 + verifier | Harness 领先 |
| **长视频（>30min）** | 2h 内单请求；更长需自行分块（或用 video-memory 插件） | 分块计划（Batch 3 待定）+ 预算循环；无层次记忆 | native 领先；video-memory 插件填补了两者都没有的"长视频记忆" |
| **工程现状** | 开箱即用（API/官方插件） | Batch 2 有 6 项评审遗留（4×P1+2×P2），live 未跑 | native 领先（成熟度） |

### 4.1 差距总结

- **native 侧的差距是"信息带宽 + 音频智能 + 成熟度"**：当前 Harness 的稀疏采样 + 本地 Whisper 在"忠实还原视频内容"这个任务目标上天然吃亏，尤其多说话人、音效、音乐类内容。qwen3.8-omni-flash 把这个差距进一步拉大（DER 88→3.4）。
- **Harness 侧的差距是"运行可信度"**：预算、审计、隐私、复现、失败语义——这些 native/官方插件都不提供。这正是 Vidsnap 应该坚守并公开度量的维度。
- **实验设计层面的差距**：9-12 计划假设"native=旧一代 omni、单发、贵"，三个假设在 9-18 之后全部动摇（新一代、agent 化、便宜）。**不更新 pin 就跑 live，实验结论的效力会大打折扣。**

---

## 5. 恢复对比实验的行动建议（决策点按顺序）

### 决策点 D1：native 路线模型 pin（需要你批准，计划规定不得自动换模型）
- **建议**：主 native 路线改为 `qwen3.8-omni-flash`（北京 DashScope compatible-mode），同时保留 `qwen3.5-omni-plus` 作为可选第三路（若想量化"一代差距"）。`native_video.py` 的 `NATIVE_VIDEO_MODEL` 常量、identity 记录、评审报告模板需同步（Qoder 执行）。
- 新增参数决策：`reasoning_effort` 显式设定（建议先 `medium` 或 `low` 控制成本/时延，另跑一次 `xhigh` 对照），并如实写入 RunBundle 的 allowlisted 配置——**不能依赖默认值**（默认 xhigh + preserve_thinking 会推高成本且跨轮携带 thinking token）。

### 决策点 D2：usage 记账扩展
- 新模型 usage 含 `prompt_tokens_details`（text/audio/video 分模态）与 `completion_tokens_details`。`ProviderUsage` 契约与聚合器需要能记录分模态明细（缺失仍记 unknown，不伪造——顺手把 P2 #5 一起修）。

### 决策点 D3：是否加入官方基线 route 0
- 低成本选项：用 `omni-video2note`（或 `api` 插件的 `perceive_media`）对同一片段出一份官方现成产物，作为"外部参照系"。好处：评审报告能回答"我们自研 Harness 相对官方全家桶处于什么位置"；代价：引入 `~/.qwen-mm-plugins/config` 依赖与额外凭证路径，需过 secret_scan 与凭证边界审查。**建议加，但放在首对 live 成功之后**（保持 Batch 3 的"一次一对、失败即停"纪律）。

### 决策点 D4：Batch 3 全片策略重估
- 新模型 2h/2GB URL 上限 → remobi 全片可能**单请求覆盖**，"确定性分块计划"或可整段删除或降级为 fallback（>2h 或无公网 URL 时才分块）。这能砍掉 Batch 3 一半以上的复杂度。

### 前置工程项（D1–D4 拍板后由 Qoder 执行，顺序即优先级）
1. 修 P1 #1：实验专用 fail-fast policy（禁格式重试与修复轮），配置记录生效策略真值；
2. 修 P1 #2：kernel 在执行插件**前**校验剩余帧余量；
3. 修 P1 #3：native 流形状校验 + 非预期异常安全终结 + 已收 usage 带入失败信封；
4. 修 P1 #4：ASR 执行记录即时持久化进 bundle；导出失败单独记录、不吞已完成段；
5. 修 P2 #5/#6：usage 缺失语义 + call_review 嵌入式路径脱敏（标点/括号/file:// /双反斜杠）；
6. 按 D1/D2 更新 native provider pin 与 usage 契约；
7. 跑 8 项仓库门禁（ruff format/check、mypy、pytest、build、conformance、secret_scan、git diff --check）→ 才进入 119s live。

### 风险提示
- **混淆变量声明必须更新**：原计划写"native 有音轨、Harness ASR 是本地模型，这是方案对比而非模型对等对比"。新数据（DER 3.4 vs 本地 Whisper 无分离能力）让这句话的分量更重——报告里要明确"native 侧音频优势来自模型代际 + 模态原生性，Harness 侧可通过换 Fun-ASR/omni_asr 时间戳接口部分追平，但那会改变'本地隐私'属性"。
- **成本核算陷阱**：`preserve_thinking` 默认开，多轮场景历史 thinking 计入输入费用；多模态输入把输出单价抬高 84%（国际区）。评审报告的 cost 段要按分模态明细算，不能用单一 token 均价。
- **定价数字时效**：本报告 CNY 分模态完整价目未能在文档抓取中全部核实（¥0.8/M 音频输入来自发布报道口径），live 前应在百炼控制台按北京地域拉一次权威价目并记录进 RunBundle 环境 allowlist。

---

## 6. 参考来源

1. 百炼官方模型页：`qwen3.8-omni-flash`（alibabacloud.com/help/zh/model-studio/qwen3-8-omni-flash，更新 2026-09-17）
2. 百炼 Qwen-Omni 家族文档（help.aliyun.com/zh/model-studio/qwen-omni，更新 2026-09-18）
3. 百炼模型定价页（help.aliyun.com/zh/model-studio/model-pricing，更新 2026-09-20；qwen3.8-max 北京 ¥12/¥36 每百万 token）
4. Qwen 官方博客发布公告 "Qwen3.8-Omni-Flash: Omni Senses. Agentic Delivery."（qwen.ai/blog?id=qwen3.8-omni-flash，2026-09-18；基准表、降价口径、Realtime 指标、MM-Plugins/Live-Harness 开源清单）
5. Qwen-MM-Plugins Hub（qwenlm.github.io/qwen-mm-plugins-hub/：core/api/video-memory/omni-video2note 等 13 插件的 Skill 与工具清单）+ GitHub 仓库 README（安装/harness 支持/配置）
6. aireiter 定价拆解（新加坡区 USD 分模态价目，2026-09-18）
7. 知乎发布解读（音频 ¥18→¥0.8/M、Live-Harness/MM-Plugins 功能介绍，2026-09-18）；新浪/凤凰科技发布报道（2026-09-18/19）
8. 本地仓库：`docs/superpowers/plans/2026-09-12-native-video-comparison.md`、`src/vidsnap/{providers,runtime,plugins}/`、`scripts/native_video_review.py`、Codex 会话档案 2026-09（三轮评审记录）

> 标注"估算"的成本数字基于文档口径推算，非账单实测；live 跑完后以 RunBundle 实测 usage 与百炼账单为准。
