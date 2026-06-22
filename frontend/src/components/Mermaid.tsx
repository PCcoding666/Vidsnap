/**
 * Mermaid 图渲染组件。
 *
 * 笔记里没有合适关键帧时，后端会让模型生成 ```mermaid 代码块作为示意图，
 * 这里把代码渲染成 SVG。渲染失败（模型偶发语法错误）时优雅降级为代码文本。
 */
import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "strict",
});

let seq = 0;

export default function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const id = `mmd-${seq++}`;
    mermaid
      .render(id, chart)
      .then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setError("");
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "图渲染失败");
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (error) {
    return (
      <pre className="text-[11px] text-amber-400 bg-slate-900/60 border border-slate-800 rounded p-2 overflow-auto">
        ⚠ 示意图渲染失败，原始定义：{"\n"}
        {chart}
      </pre>
    );
  }

  return <div ref={ref} className="my-3 flex justify-center [&_svg]:max-w-full" />;
}
