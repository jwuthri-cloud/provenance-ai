import type { ReactNode } from "react";

import { badgeColor, fmtDay, sourceMeta, splitByCategory } from "../lib/format";
import type { TimelineDay } from "../lib/trace";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-white/10 bg-white/[0.02] ${className}`}>{children}</div>
  );
}

export function StatCard({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <Card className="px-5 py-4">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-2xl font-semibold mt-1 text-white">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </Card>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-sm font-medium text-slate-300 mb-3">{children}</h2>;
}

export function SourceBar({ by_source, height = 12 }: { by_source: Record<string, number>; height?: number }) {
  const total = Object.values(by_source).reduce((a, b) => a + b, 0) || 1;
  const entries = Object.entries(by_source).sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <div className="flex w-full overflow-hidden rounded-full" style={{ height }}>
        {entries.map(([s, n]) => (
          <div key={s} title={`${sourceMeta(s).label}: ${n} lines`}
               style={{ width: `${(100 * n) / total}%`, background: sourceMeta(s).color }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3 text-xs text-slate-400">
        {entries.map(([s, n]) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: sourceMeta(s).color }} />
            {sourceMeta(s).label}
            <span className="text-slate-500">{Math.round((100 * n) / total)}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function Donut({ ai, human, generated }: { ai: number; human: number; generated: number }) {
  const total = ai + human + generated || 1;
  const a = (100 * ai) / total;
  const h = (100 * human) / total;
  const style = {
    background: `conic-gradient(#22d3ee 0 ${a}%, #94a3b8 ${a}% ${a + h}%, #f59e0b ${a + h}% 100%)`,
  };
  return (
    <div className="flex items-center gap-6">
      <div className="relative w-28 h-28 rounded-full" style={style}>
        <div className="absolute inset-[14px] rounded-full bg-[#0a0e14] flex flex-col items-center justify-center">
          <div className="text-xl font-semibold text-white">{Math.round(a)}%</div>
          <div className="text-[10px] text-slate-500">AI</div>
        </div>
      </div>
      <div className="text-xs space-y-1.5">
        <Legend color="#22d3ee" label="AI" v={ai} />
        <Legend color="#94a3b8" label="Human" v={human} />
        <Legend color="#f59e0b" label="Generated" v={generated} />
      </div>
    </div>
  );
}

function Legend({ color, label, v }: { color: string; label: string; v: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
      <span className="text-slate-300 w-16">{label}</span>
      <span className="text-slate-500">{v} lines</span>
    </div>
  );
}

export function ConfidenceBadge({ badge }: { badge: string }) {
  const c = badgeColor(badge);
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ background: c + "22", color: c }}>
      {badge}
    </span>
  );
}

export function Flag() {
  return <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400">⚑ high AI</span>;
}

export function TimelineChart({ days }: { days: TimelineDay[] }) {
  const max = Math.max(1, ...days.map((d) => d.lines));
  return (
    <div className="flex items-end gap-3 h-32 pt-2">
      {days.map((d) => {
        const { ai, human, generated } = splitByCategory(d.by_source);
        const hpx = (n: number) => Math.round((96 * n) / max);
        return (
          <div key={d.day} className="flex flex-col items-center gap-2 flex-1 min-w-0">
            <div className="flex flex-col-reverse w-full max-w-[42px] rounded overflow-hidden" title={`${d.lines} lines`}>
              <div style={{ height: hpx(ai), background: "#22d3ee" }} />
              <div style={{ height: hpx(human), background: "#94a3b8" }} />
              <div style={{ height: hpx(generated), background: "#f59e0b" }} />
            </div>
            <div className="text-[10px] text-slate-500 whitespace-nowrap">{fmtDay(d.day)}</div>
          </div>
        );
      })}
    </div>
  );
}

export function DaemonDown() {
  return (
    <Card className="px-6 py-10 text-center">
      <div className="text-lg text-white mb-2">No daemon connection</div>
      <div className="text-sm text-slate-400 max-w-md mx-auto">
        The dashboard reads the local trace daemon. Start it and seed some data:
      </div>
      <pre className="text-xs text-cyan-300 bg-black/30 rounded-lg px-4 py-3 mt-4 inline-block text-left">
{`TRACE_HOME=/tmp/trace-demo uv run python scripts/seed_demo.py
TRACE_HOME=/tmp/trace-demo uv run trace-daemon`}
      </pre>
    </Card>
  );
}
