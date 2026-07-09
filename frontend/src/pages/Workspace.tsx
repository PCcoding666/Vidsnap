/**
 * VidSnap 主工作台（深色工具链设计语言，源自 /lab，升为主产品界面）
 *
 * 三栏：
 *  左  — 视频 + 目标 + 工具补充 + 本地历史（localStorage，无需登录）
 *  中  — 工具调用链路 trace（状态点/耗时/输出）+ 关键帧画廊
 *  右  — 产物 artifact 正文（深色 markdown + mermaid）+ AI 聊天（基于 /qa）
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiClient } from "@/services/api";
import Mermaid from "@/components/Mermaid";
import type {
  WorkspacePlan,
  WorkspaceJobStatus,
  WorkspaceJobArtifactResponse,
  WorkspaceSkillTrace,
} from "@/services/api";

interface LabSkill {
  name: string;
  description: string;
  cost_estimate: "low" | "medium" | "high";
  default_enabled: boolean;
}

interface FrameRef {
  timestamp: number;
  segment_index?: number;
  start_time?: number;
  end_time?: number;
  text?: string;
  reason: string;
  frame_url: string;
  frame_type?: string;
  ocr_text?: string;
  zoom_url?: string | null;
}

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

interface HistItem {
  jobId: string;
  title: string;
  query: string;
  ts: number;
}

const SUPPLEMENTABLE = new Set<string>(["ExtractFrames"]);

const QUICK_QUERIES = [
  "把这个视频整理成可复用的结构化笔记",
  "用图文笔记总结，关键步骤配截图",
  "按时间线整理重点，并标注时间戳",
];

// 斜杠命令（AI-native 触发 skill；输入 / 唤起）
const SLASH_COMMANDS = [
  { cmd: "/youtube", desc: "下载并分析 YouTube 视频", hint: "/youtube <链接> <目标>" },
];

const STATUS_STYLE: Record<string, { dot: string; label: string; text: string }> = {
  planned: { dot: "bg-slate-500", label: "待执行", text: "text-slate-400" },
  running: { dot: "bg-amber-400 animate-pulse", label: "执行中", text: "text-amber-300" },
  success: { dot: "bg-emerald-400", label: "完成", text: "text-emerald-300" },
  skipped: { dot: "bg-slate-600", label: "跳过", text: "text-slate-500" },
  failed: { dot: "bg-rose-500", label: "失败", text: "text-rose-300" },
};

const HISTORY_KEY = "vidsnap_history";

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function fmtAgo(ts: number): string {
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return new Date(ts).toLocaleDateString();
}

function loadHist(): HistItem[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveHist(item: HistItem): HistItem[] {
  const cur = loadHist().filter((h) => h.jobId !== item.jobId);
  const next = [item, ...cur].slice(0, 20);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  return next;
}

// 去掉正文里的「Visual References」内联图——右侧画廊已交互式展示，避免重复。
function stripVisualReferences(md: string): string {
  return md.replace(/\n*##\s*Visual References[\s\S]*?(?=\n##\s|$)/g, "\n").trim();
}

export default function Workspace() {
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [slashOpen, setSlashOpen] = useState(false);
  const [query, setQuery] = useState<string>("把这个视频整理成可复用的结构化笔记");
  const [skills, setSkills] = useState<LabSkill[]>([]);
  const [forceSkills, setForceSkills] = useState<Set<string>>(new Set());
  const [visualMode, setVisualMode] = useState<"auto" | "on" | "off">("auto");
  const [plan, setPlan] = useState<WorkspacePlan | null>(null);

  const [jobId, setJobId] = useState<string>("");
  const [job, setJob] = useState<WorkspaceJobStatus | null>(null);
  const [artifact, setArtifact] = useState<WorkspaceJobArtifactResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string>("");

  const [history, setHistory] = useState<HistItem[]>([]);
  const [chatMsgs, setChatMsgs] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pollRef = useRef<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const queryRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => setHistory(loadHist()), []);

  // 加载技能注册表
  useEffect(() => {
    apiClient
      .get<{ skills: LabSkill[] }>("/workspace/skills")
      .then((d) => setSkills(d.skills))
      .catch(() => {});
  }, []);

  // query / forceSkills 变化时预览链路（debounce）
  useEffect(() => {
    if (!query.trim()) {
      setPlan(null);
      return;
    }
    const handle = window.setTimeout(() => {
      apiClient
        .post<{ plan: WorkspacePlan }>("/workspace/plan", {
          query: query.trim(),
          force_skills: Array.from(forceSkills),
          visual_mode: visualMode,
        })
        .then((d) => setPlan(d.plan))
        .catch(() => setPlan(null));
    }, 350);
    return () => window.clearTimeout(handle);
  }, [query, forceSkills, visualMode]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMsgs]);

  const onPickFile = (f: File | null) => {
    setFile(f);
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setVideoUrl(f ? URL.createObjectURL(f) : "");
    setJob(null);
    setArtifact(null);
    setJobId("");
    setError("");
    setChatMsgs([]);
  };

  const toggleForce = (name: string) => {
    setForceSkills((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const stopPolling = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const fetchArtifact = useCallback(async (id: string) => {
    try {
      const a = await apiClient.get<WorkspaceJobArtifactResponse>(
        `/workspace/jobs/${id}/artifact`,
      );
      setArtifact(a);
      return a;
    } catch {
      return null;
    }
  }, []);

  const run = async () => {
    // 解析斜杠命令：/youtube <url> <目标>；否则整句是目标
    const cmd = query.trim().match(/^\/youtube\s+(\S+)\s*([\s\S]*)$/i);
    const cmdUrl = cmd ? cmd[1] : "";
    const goal = cmd ? (cmd[2].trim() || "把这个视频整理成可复用的结构化笔记") : query.trim();
    if ((!file && !cmdUrl) || !goal || running) return;
    setRunning(true);
    setError("");
    setArtifact(null);
    setJob(null);
    setChatMsgs([]);
    try {
      const fd = new FormData();
      if (file) fd.append("video_file", file);
      if (cmdUrl) fd.append("video_url", cmdUrl);
      fd.append("query", goal);
      fd.append("provider", "paraformer");
      fd.append("force_skills", Array.from(forceSkills).join(","));
      fd.append("visual_mode", visualMode);

      const created = await apiClient.postFormData<{ job_id: string; job: WorkspaceJobStatus }>(
        "/workspace/jobs",
        fd,
      );
      setJobId(created.job_id);
      setJob(created.job);

      stopPolling();
      pollRef.current = window.setInterval(async () => {
        try {
          const res = await apiClient.get<{ job: WorkspaceJobStatus }>(
            `/workspace/jobs/${created.job_id}`,
          );
          setJob(res.job);
          if (res.job.status === "succeeded") {
            stopPolling();
            setRunning(false);
            const a = await fetchArtifact(created.job_id);
            const title = a?.artifact?.title || file?.name || "未命名";
            setHistory(saveHist({ jobId: created.job_id, title, query: query.trim(), ts: Date.now() }));
          } else if (res.job.status === "failed" || res.job.status === "canceled") {
            stopPolling();
            setRunning(false);
            setError(res.job.error || "任务失败");
          }
        } catch (e) {
          stopPolling();
          setRunning(false);
          setError(e instanceof Error ? e.message : "轮询失败");
        }
      }, 2500);
    } catch (e) {
      setRunning(false);
      setError(e instanceof Error ? e.message : "提交失败");
    }
  };

  const openHistory = async (item: HistItem) => {
    setError("");
    setChatMsgs([]);
    setJobId(item.jobId);
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setVideoUrl("");
    setFile(null);
    setQuery(item.query);
    try {
      const res = await apiClient.get<{ job: WorkspaceJobStatus }>(`/workspace/jobs/${item.jobId}`);
      setJob(res.job);
      await fetchArtifact(item.jobId);
    } catch {
      setError("该历史记录已不可用（后端重启会清空内存态 job）");
      setJob(null);
      setArtifact(null);
    }
  };

  const sendChat = async () => {
    const q = chatInput.trim();
    if (!q || !jobId || chatSending) return;
    setChatMsgs((m) => [...m, { role: "user", content: q }]);
    setChatInput("");
    setChatSending(true);
    try {
      const r = await apiClient.post<{ answer: string }>(`/workspace/jobs/${jobId}/qa`, {
        question: q,
        top_k: 5,
      });
      setChatMsgs((m) => [...m, { role: "assistant", content: r.answer || "（无答案）" }]);
    } catch (e) {
      setChatMsgs((m) => [
        ...m,
        { role: "assistant", content: "⚠ " + (e instanceof Error ? e.message : "提问失败") },
      ]);
    } finally {
      setChatSending(false);
    }
  };

  useEffect(() => () => stopPolling(), []);

  const steps = job?.plan?.steps ?? plan?.steps ?? [];
  const traceByStep = useMemo(() => {
    const map = new Map<string, WorkspaceSkillTrace>();
    (job?.skill_trace ?? []).forEach((t) => map.set(t.step_id, t));
    return map;
  }, [job]);

  const frames: FrameRef[] = useMemo(() => {
    const meta = artifact?.artifact?.metadata as { frames?: FrameRef[] } | undefined;
    return meta?.frames ?? [];
  }, [artifact]);

  const seekTo = (t: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = t;
      videoRef.current.play().catch(() => {});
    }
  };

  const planInPlan = (name: string) => steps.some((s) => s.skill === name);
  const canChat = job?.status === "succeeded" && !!jobId;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-sm">🎬</div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight">
              VidSnap <span className="text-slate-500 font-normal">工作台</span>
            </h1>
          </div>
        </div>
        <span className="text-xs text-slate-600">本地视频 → 可复用文本资产 · 转录为唯一真相源</span>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr_400px] gap-0 h-[calc(100vh-53px)]">
        {/* 左：视频 + 目标 + 工具 + 历史 */}
        <section className="border-r border-slate-800 p-5 space-y-4 overflow-y-auto">
          <div className="aspect-video w-full rounded-lg overflow-hidden bg-black flex items-center justify-center">
            {videoUrl ? (
              <video ref={videoRef} src={videoUrl} controls className="h-full w-full" />
            ) : (
              <label className="cursor-pointer text-center text-slate-500 hover:text-slate-300 transition w-full h-full flex flex-col items-center justify-center">
                <input type="file" accept="video/*" className="hidden" onChange={(e) => onPickFile(e.target.files?.[0] ?? null)} />
                <div className="text-3xl mb-1">＋</div>
                <div className="text-xs">点击上传本地视频</div>
                <div className="text-[10px] text-slate-600 mt-1">MP4 / MOV / MKV / AVI / WEBM / M4V</div>
              </label>
            )}
          </div>
          {videoUrl && (
            <label className="inline-block text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer">
              <input type="file" accept="video/*" className="hidden" onChange={(e) => onPickFile(e.target.files?.[0] ?? null)} />
              更换视频 · {file?.name}
            </label>
          )}

          <div className="relative">
            <label className="text-xs text-slate-400 mb-1 block">你的目标（自然语言，输入 / 唤起命令）</label>
            <textarea
              ref={queryRef}
              value={query}
              onChange={(e) => {
                const v = e.target.value;
                setQuery(v);
                setSlashOpen(/^\/[a-z]*$/i.test(v.trim()));
              }}
              onKeyDown={(e) => {
                if (slashOpen && (e.key === "Tab" || e.key === "Enter")) {
                  const match = SLASH_COMMANDS.find((c) => c.cmd.startsWith(query.trim().toLowerCase()));
                  if (match) {
                    e.preventDefault();
                    setQuery(match.cmd + " ");
                    setSlashOpen(false);
                  }
                }
              }}
              rows={3}
              className="w-full rounded-lg bg-slate-900 border border-slate-800 p-3 text-sm resize-none focus:outline-none focus:border-slate-600"
              placeholder="例如：把视频整理成带截图的结构化笔记；或输入 / 唤起命令（如 /youtube）"
            />
            {slashOpen && SLASH_COMMANDS.some((c) => c.cmd.startsWith(query.trim().toLowerCase())) && (
              <div className="absolute z-30 left-0 right-0 mt-1 rounded-lg border border-slate-700 bg-slate-900 shadow-xl overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] text-slate-600 border-b border-slate-800">命令 · Tab/Enter 选中</div>
                {SLASH_COMMANDS.filter((c) => c.cmd.startsWith(query.trim().toLowerCase())).map((c) => (
                  <button
                    key={c.cmd}
                    type="button"
                    onClick={() => { setQuery(c.cmd + " "); setSlashOpen(false); queryRef.current?.focus(); }}
                    className="w-full text-left px-3 py-2 hover:bg-slate-800 flex items-center gap-2"
                  >
                    <span className="text-emerald-400 text-sm font-mono">{c.cmd}</span>
                    <span className="text-xs text-slate-500">{c.desc}</span>
                    <span className="ml-auto text-[10px] text-slate-600 font-mono">{c.hint}</span>
                  </button>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-1.5 mt-2">
              {QUICK_QUERIES.map((q) => (
                <button
                  key={q}
                  onClick={() => setQuery(q)}
                  className="text-[11px] px-2 py-1 rounded-md border border-slate-800 bg-slate-900/50 text-slate-400 hover:text-slate-200 hover:border-slate-600 transition"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {/* 画面截帧模式：帧是计划驱动的可选项（auto/on/off） */}
          <div>
            <div className="text-xs text-slate-400 mb-2">
              画面截帧 <span className="text-slate-600">（图文笔记里的关键帧）</span>
            </div>
            <div className="flex rounded-lg border border-slate-800 overflow-hidden text-xs">
              {([
                ["auto", "自动"],
                ["on", "强制"],
                ["off", "关闭"],
              ] as const).map(([m, label]) => (
                <button
                  key={m}
                  onClick={() => setVisualMode(m)}
                  className={`flex-1 py-1.5 transition ${visualMode === m ? "bg-emerald-600 text-white" : "bg-slate-900/50 text-slate-400 hover:text-slate-200"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="text-[11px] text-slate-600 mt-1">
              {visualMode === "auto" && "按目标里的“图文/截图”等词自动决定是否截帧"}
              {visualMode === "on" && "强制生成带关键帧的图文笔记"}
              {visualMode === "off" && "纯文本，不做任何截帧/画面分析"}
            </div>
          </div>

          {/* 工具补充 */}
          {skills.some((s) => SUPPLEMENTABLE.has(s.name)) && (
            <div>
              <div className="text-xs text-slate-400 mb-2">
                工具补充 <span className="text-slate-600">（planner 没自动选的可选工具）</span>
              </div>
              <div className="space-y-2">
                {skills
                  .filter((s) => SUPPLEMENTABLE.has(s.name))
                  .map((s) => {
                    const autoIncluded = planInPlan(s.name) && !forceSkills.has(s.name);
                    const on = forceSkills.has(s.name) || autoIncluded;
                    return (
                      <div key={s.name} className="flex items-start justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium">{s.name}</div>
                          <div className="text-xs text-slate-500 mt-0.5">{s.description}</div>
                          {autoIncluded && <div className="text-[11px] text-emerald-400 mt-1">planner 已自动选择</div>}
                        </div>
                        <button
                          onClick={() => toggleForce(s.name)}
                          disabled={autoIncluded}
                          className={`shrink-0 h-6 w-11 rounded-full transition relative ${on ? "bg-emerald-500" : "bg-slate-700"} ${autoIncluded ? "opacity-50 cursor-not-allowed" : ""}`}
                        >
                          <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
                        </button>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          <button
            onClick={run}
            disabled={(!file && !/^\/youtube\s+\S+/i.test(query.trim())) || !query.trim() || running}
            className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-600 py-2.5 text-sm font-medium transition"
          >
            {running ? `执行中… ${job?.progress ?? 0}%` : "运行工具链"}
          </button>
          {error && <div className="text-xs text-rose-400">⚠ {error}</div>}

          {/* 本地历史 */}
          <div className="pt-2 border-t border-slate-800">
            <div className="text-xs text-slate-400 mb-2 flex items-center gap-1.5">
              <span>历史记录</span>
              <span className="text-slate-600">（本地，无需登录）</span>
            </div>
            {history.length === 0 ? (
              <div className="text-[11px] text-slate-600 py-2">还没有分析记录</div>
            ) : (
              <div className="space-y-1">
                {history.map((h) => (
                  <button
                    key={h.jobId}
                    onClick={() => openHistory(h)}
                    className={`w-full text-left rounded-md px-2.5 py-2 transition border ${jobId === h.jobId ? "border-emerald-700 bg-emerald-950/30" : "border-transparent hover:bg-slate-900/60"}`}
                  >
                    <div className="text-xs text-slate-200 line-clamp-1">{h.title}</div>
                    <div className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">{h.query}</div>
                    <div className="text-[10px] text-slate-600 mt-0.5">{fmtAgo(h.ts)}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* 中：工具链路 + 关键帧 */}
        <section className="p-5 space-y-5 overflow-y-auto">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">工具调用链路</h2>
            {plan && (
              <span className="text-xs text-slate-500">
                产物：<span className="text-slate-300">{plan.artifact_type}</span> · 成本 {plan.cost_tier}
              </span>
            )}
          </div>

          {steps.length === 0 ? (
            <div className="text-sm text-slate-600 py-10 text-center border border-dashed border-slate-800 rounded-lg">
              上传视频、输入目标后，模型规划的工具链路会在这里可视化
            </div>
          ) : (
            <ol className="space-y-1">
              {steps.map((step, i) => {
                const t = traceByStep.get(step.id);
                const status = t?.status ?? "planned";
                const st = STATUS_STYLE[status] ?? STATUS_STYLE.planned;
                const forced = forceSkills.has(step.skill) && SUPPLEMENTABLE.has(step.skill);
                return (
                  <li key={step.id}>
                    <div className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <span className={`h-3 w-3 rounded-full ${st.dot} mt-1.5`} />
                        {i < steps.length - 1 && <span className="w-px flex-1 bg-slate-800 my-1" />}
                      </div>
                      <div className="flex-1 rounded-lg border border-slate-800 bg-slate-900/40 p-3 mb-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium">
                            {step.skill}
                            {forced && <span className="ml-2 text-[11px] text-emerald-400">手动补充</span>}
                          </span>
                          <span className={`text-[11px] ${st.text}`}>{st.label}</span>
                        </div>
                        <div className="text-xs text-slate-500 mt-1">{step.purpose}</div>
                        {t?.output_summary && <div className="text-[11px] text-slate-400 mt-1.5">↳ {t.output_summary}</div>}
                        {t?.duration_ms != null && <div className="text-[11px] text-slate-600 mt-0.5">{(t.duration_ms / 1000).toFixed(1)}s</div>}
                        {t?.error && <div className="text-[11px] text-rose-400 mt-1">{t.error}</div>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}

          {frames.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-2">
                模型选出的关键帧 <span className="text-slate-600">({frames.length})</span>
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {frames.map((f, i) => (
                  <div key={i} className="space-y-1">
                    <button onClick={() => seekTo(f.timestamp)} className="text-left group block w-full" title="点击跳转到视频对应时间点">
                      <img src={f.frame_url} alt={`frame@${f.timestamp}`} className="w-full rounded-md border border-slate-800 group-hover:border-emerald-500 transition" />
                      <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1.5">
                        <span className="text-emerald-400">{fmtTime(f.timestamp)}</span>
                        {f.frame_type && <span className="px-1 rounded bg-slate-800 text-slate-400">{f.frame_type}</span>}
                      </div>
                      <div className="text-[11px] text-slate-400">{f.reason}</div>
                    </button>
                    {f.ocr_text && (
                      <div className="text-[11px] text-slate-500 bg-slate-900/60 border border-slate-800 rounded px-1.5 py-1">📃 {f.ocr_text}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* 右：产物 + AI 聊天 */}
        <section className="border-l border-slate-800 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-2">产物</h2>
            {artifact?.artifact?.content ? (
              <>
                <div className="text-xs text-slate-500 mb-2">{artifact.artifact.title}</div>
                <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 prose prose-sm prose-invert max-w-none prose-headings:text-slate-100 prose-p:text-slate-300 prose-li:text-slate-300 prose-strong:text-slate-100 prose-a:text-emerald-400 prose-img:rounded-md prose-img:border prose-img:border-slate-800">
                  <ReactMarkdown
                    urlTransform={(u) => u}
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code({ className, children }) {
                        if (/language-mermaid/.test(className || "")) {
                          return <Mermaid chart={String(children).replace(/\n$/, "")} />;
                        }
                        return <code className={className}>{children}</code>;
                      },
                    }}
                  >
                    {stripVisualReferences(artifact.artifact.content)}
                  </ReactMarkdown>
                </div>
              </>
            ) : (
              <div className="text-sm text-slate-600 py-10 text-center border border-dashed border-slate-800 rounded-lg">
                运行完成后，生成的笔记/摘要产物会在这里显示
              </div>
            )}
          </div>

          {/* AI 聊天 */}
          <div className="border-t border-slate-800 flex flex-col" style={{ maxHeight: "45%" }}>
            <div className="px-5 py-2.5 text-xs font-semibold text-slate-300 flex items-center gap-2 border-b border-slate-800/60">
              <span className="text-indigo-400">✦</span> AI 助手
              {!canChat && <span className="text-slate-600 font-normal">（分析完成后可对视频提问）</span>}
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3 min-h-[80px]">
              {chatMsgs.length === 0 ? (
                <div className="text-[11px] text-slate-600">
                  {canChat ? "就这个视频问我任何问题，答案基于转录内容。" : "先上传并分析一个视频。"}
                </div>
              ) : (
                chatMsgs.map((m, i) => (
                  <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap ${
                        m.role === "user" ? "bg-emerald-600 text-white" : "bg-slate-900 border border-slate-800 text-slate-300"
                      }`}
                    >
                      {m.content}
                    </div>
                  </div>
                ))
              )}
              {chatSending && <div className="text-[11px] text-slate-500">思考中…</div>}
              <div ref={chatEndRef} />
            </div>
            <div className="p-3 border-t border-slate-800/60 flex gap-2">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendChat()}
                disabled={!canChat || chatSending}
                placeholder={canChat ? "问关于这个视频的问题…" : "分析完成后可用"}
                className="flex-1 rounded-lg bg-slate-900 border border-slate-800 px-3 py-2 text-xs focus:outline-none focus:border-slate-600 disabled:opacity-50"
              />
              <button
                onClick={sendChat}
                disabled={!canChat || chatSending || !chatInput.trim()}
                className="rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 px-3 text-xs transition"
              >
                发送
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
