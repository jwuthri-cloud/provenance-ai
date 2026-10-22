import Link from "next/link";

import {
  Card, DaemonDown, Donut, SectionTitle, SourceBar, StatCard, TimelineChart,
} from "../components/ui";
import { fmtTime, shortHash, sourceMeta } from "../lib/format";
import { getOverview, getTimeline } from "../lib/trace";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const ov = await getOverview();
  if (!ov) return <DaemonDown />;
  const timeline = (await getTimeline())?.timeline ?? [];

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-xl font-semibold text-white">Overview</h1>
        <p className="text-sm text-slate-500">
          {ov.repos} repo{ov.repos === 1 ? "" : "s"} · chain {shortHash(ov.chain_head)} · daemon v{ov.version}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="AI-authored" value={`${ov.ai_pct}%`} sub={`${ov.ai_lines} of ${ov.total_lines} lines`} />
        <StatCard label="Events" value={ov.events} sub={`${ov.files} files`} />
        <StatCard label="Sessions" value={ov.sessions} />
        <StatCard label="Models" value={ov.models.length} sub={ov.models.join(", ") || "—"} />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card className="px-5 py-5">
          <SectionTitle>Authorship by source</SectionTitle>
          <SourceBar by_source={ov.by_source} />
        </Card>
        <Card className="px-5 py-5">
          <SectionTitle>AI vs human vs generated</SectionTitle>
          <Donut ai={ov.ai_lines} human={ov.human_lines} generated={ov.generated_lines} />
        </Card>
      </div>

      {timeline.length > 0 && (
        <Card className="px-5 py-5">
          <SectionTitle>Authorship over time</SectionTitle>
          <TimelineChart days={timeline} />
        </Card>
      )}

      <Card className="px-5 py-5">
        <SectionTitle>Recent activity</SectionTitle>
        <div className="divide-y divide-white/5">
          {ov.recent.map((r, i) => (
            <div key={i} className="flex items-center gap-3 py-2 text-sm">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: sourceMeta(r.source).color }} />
              <Link href={`/files`} className="text-slate-200 hover:text-white truncate">{r.file}</Link>
              <span className="text-slate-500 text-xs">{sourceMeta(r.source).label}</span>
              {r.model && <span className="text-cyan-400/80 text-xs">{r.model}</span>}
              <span className="ml-auto text-slate-500 text-xs whitespace-nowrap">{r.lines} ln · {fmtTime(r.ts)}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
