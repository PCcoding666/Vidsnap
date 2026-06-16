/**
 * VidSnap 测试空间（Lab）
 *
 * 全新设计，与旧前端无关。左：视频 + 目标输入；右：工具调用链路可视化。
 * 核心交互：planner 自动选工具后，用户可手动「补充」可选工具（如 ExtractFrames），
 * 后端 force_skills 会尊重补充并改写执行链路。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/services/api";
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
  segment_index: number;
  start_time: number;
  end_time: number;
  text: string;
  reason: string;
  frame_url: string;
}

// 可被用户「补充」的可选工具（planner 不一定自动选）。
const SUPPLEMENTABLE = new Set<string>(["ExtractFrames"]);

const STATUS_STYLE: Record<string, { dot: string; label: string; text: string }> = {
  planned: { dot: "bg-slate-500", label: "待执行", text: "text-slate-400" },
  running: { dot: "bg-amber-400 animate-pulse", label: "执行中", text: "text-amber-300" },
  success: { dot: "bg-emerald-400", label: "完成", text: "text-emerald-300" },
  skipped: { dot: "bg-slate-600", label: "跳过", text: "text-slate-500" },
  failed: { dot: "bg-rose-500", label: "失败", text: "text-rose-300" },
};

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export default function Lab() {
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [query, setQuery] = useState<string>("帮我整理成带截图的学习笔记");
  const [skills, setSkills] = useState<LabSkill[]>([]);
  const [forceSkills, setForceSkills] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<WorkspacePlan | null>(null);

  const [jobId, setJobId] = useState<string>("");
  const [job, setJob] = useState<WorkspaceJobStatus | null>(null);
  const [artifact, setArtifact] = useState<WorkspaceJobArtifactResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string>("");

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pollRef = useRef<number | null>(null);

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
        })
        .then((d) => setPlan(d.plan))
        .catch(() => setPlan(null));
    }, 350);
    return () => window.clearTimeout(handle);
  }, [query, forceSkills]);

  const onPickFile = (f: File | null) => {
    setFile(f);
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setVideoUrl(f ? URL.createObjectURL(f) : "");
    // 重置上次运行
    setJob(null);
    setArtifact(null);
    setJobId("");
    setError("");
  };

  const toggleForce = (name: string) => {
    setForceSkills((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
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
    } catch {
      /* 产物可能尚未就绪 */
    }
  }, []);

  const run = async () => {
    if (!file || !query.trim() || running) return;
    setRunning(true);
    setError("");
    setArtifact(null);
    setJob(null);
    try {
      const fd = new FormData();
      fd.append("video_file", file);
      fd.append("query", query.trim());
      fd.append("provider", "paraformer");
      fd.append("force_skills", Array.from(forceSkills).join(","));

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
            fetchArtifact(created.job_id);
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

  useEffect(() => () => stopPolling(), []);

  // 链路节点：优先用 job（执行态），否则用 plan 预览
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

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-lg font-semibold tracking-tight">
          VidSnap 测试空间 <span className="text-slate-500 text-sm">/ Tool-Chain Lab</span>
        </h1>
        <p className="text-xs text-slate-500 mt-1">
          左：视频与目标 · 右：工具调用链路可视化 · 可在 planner 自动选工具后手动补充工具
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0">
        {/* 左：视频 + 控制 */}
        <section className="border-r border-slate-800 p-6 space-y-5">
          <div className="aspect-video w-full rounded-lg overflow-hidden bg-black flex items-center justify-center">
            {videoUrl ? (
              <video ref={videoRef} src={videoUrl} controls className="h-full w-full" />
            ) : (
              <label className="cursor-pointer text-center text-slate-500 hover:text-slate-300 transition">
                <input
                  type="file"
                  accept="video/*"
                  className="hidden"
                  onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
                />
                <div className="text-4xl mb-2">＋</div>
                <div className="text-sm">点击上传本地视频</div>
              </label>
            )}
          </div>
          {videoUrl && (
            <label className="inline-block text-xs text-slate-400 hover:text-slate-200 cursor-pointer">
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
              />
              更换视频 · {file?.name}
            </label>
          )}

          <div>
            <label className="text-xs text-slate-400 mb-1 block">你的目标（自然语言）</label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={3}
              className="w-full rounded-lg bg-slate-900 border border-slate-800 p-3 text-sm resize-none focus:outline-none focus:border-slate-600"
              placeholder="例如：把视频整理成带截图的结构化笔记"
            />
          </div>

          {/* 工具补充面板 */}
          <div>
            <div className="text-xs text-slate-400 mb-2">
              工具补充 <span className="text-slate-600">（planner 没自动选的可选工具，手动补充）</span>
            </div>
            <div className="space-y-2">
              {skills
                .filter((s) => SUPPLEMENTABLE.has(s.name))
                .map((s) => {
                  const autoIncluded = planInPlan(s.name) && !forceSkills.has(s.name);
                  const on = forceSkills.has(s.name) || autoIncluded;
                  return (
                    <div
                      key={s.name}
                      className="flex items-start justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3"
                    >
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{s.name}</div>
                        <div className="text-xs text-slate-500 mt-0.5">{s.description}</div>
                        {autoIncluded && (
                          <div className="text-[11px] text-emerald-400 mt-1">planner 已自动选择</div>
                        )}
                      </div>
                      <button
                        onClick={() => toggleForce(s.name)}
                        disabled={autoIncluded}
                        className={`shrink-0 h-6 w-11 rounded-full transition relative ${
                          on ? "bg-emerald-500" : "bg-slate-700"
                        } ${autoIncluded ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        <span
                          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                            on ? "left-[22px]" : "left-0.5"
                          }`}
                        />
                      </button>
                    </div>
                  );
                })}
            </div>
          </div>

          <button
            onClick={run}
            disabled={!file || !query.trim() || running}
            className="w-full rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-600 py-2.5 text-sm font-medium transition"
          >
            {running ? `执行中… ${job?.progress ?? 0}%` : "运行工具链"}
          </button>
          {error && <div className="text-xs text-rose-400">⚠ {error}</div>}
        </section>

        {/* 右：工具链路可视化 */}
        <section className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">工具调用链路</h2>
            {plan && (
              <span className="text-xs text-slate-500">
                产物类型：<span className="text-slate-300">{plan.artifact_type}</span> · 成本{" "}
                {plan.cost_tier}
              </span>
            )}
          </div>

          {steps.length === 0 ? (
            <div className="text-sm text-slate-600 py-8 text-center">
              输入目标后将在此预览模型规划的工具链路
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
                        {i < steps.length - 1 && (
                          <span className="w-px flex-1 bg-slate-800 my-1" />
                        )}
                      </div>
                      <div className="flex-1 rounded-lg border border-slate-800 bg-slate-900/40 p-3 mb-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium">
                            {step.skill}
                            {forced && (
                              <span className="ml-2 text-[11px] text-emerald-400">手动补充</span>
                            )}
                          </span>
                          <span className={`text-[11px] ${st.text}`}>{st.label}</span>
                        </div>
                        <div className="text-xs text-slate-500 mt-1">{step.purpose}</div>
                        {t?.output_summary && (
                          <div className="text-[11px] text-slate-400 mt-1.5">↳ {t.output_summary}</div>
                        )}
                        {t?.duration_ms != null && (
                          <div className="text-[11px] text-slate-600 mt-0.5">
                            {(t.duration_ms / 1000).toFixed(1)}s
                          </div>
                        )}
                        {t?.error && (
                          <div className="text-[11px] text-rose-400 mt-1">{t.error}</div>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}

          {/* 截帧画廊：ExtractFrames 产物 */}
          {frames.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-2">
                模型选出的关键帧 <span className="text-slate-600">({frames.length})</span>
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {frames.map((f, i) => (
                  <button
                    key={i}
                    onClick={() => seekTo(f.timestamp)}
                    className="text-left group"
                    title="点击跳转到视频对应时间点"
                  >
                    <img
                      src={f.frame_url}
                      alt={`frame@${f.timestamp}`}
                      className="w-full rounded-md border border-slate-800 group-hover:border-emerald-500 transition"
                    />
                    <div className="text-[11px] text-slate-400 mt-1">
                      <span className="text-emerald-400">{fmtTime(f.timestamp)}</span> · {f.reason}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 产物正文 */}
          {artifact?.artifact?.content && (
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-2">产物：{artifact.artifact.title}</h3>
              <pre className="whitespace-pre-wrap text-xs text-slate-300 bg-slate-900/50 border border-slate-800 rounded-lg p-3 max-h-96 overflow-auto">
                {artifact.artifact.content}
              </pre>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
