import Link from "next/link";

import { Card, ConfidenceBadge, DaemonDown, SectionTitle, SourceBar } from "../../../components/ui";
import { sourceMeta } from "../../../lib/format";
import { getFileBlame, type Span } from "../../../lib/trace";

export const dynamic = "force-dynamic";

function spanForLine(spans: Span[], line: number): Span | null {
  for (const s of spans) if (line >= s.start && line <= s.end) return s;
  return null;
}

export default async function FileView({
  searchParams,
}: {
  searchParams: Promise<{ repo_id?: string; path?: string }>;
}) {
  const sp = await searchParams;
  const repoId = sp.repo_id ?? "";
  const path = sp.path ?? "";
  if (!repoId || !path) return <div className="text-slate-400">Missing file reference.</div>;

  const blame = await getFileBlame(repoId, path);
  if (!blame) return <DaemonDown />;

  const lines = blame.text.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const aiSpans = blame.spans.filter((s) => s.prompt_excerpt || (s.model && s.source !== "human_keyboard"));

  return (
    <div className="space-y-5">
      <div>
        <Link href="/files" className="text-xs text-slate-500 hover:text-slate-300">← files</Link>
        <h1 className="text-xl font-semibold text-white font-mono mt-1">{blame.file}</h1>
        <p className="text-sm text-slate-500">
          {blame.lines} lines · {blame.summary.models.join(", ") || "no model"}
          {!blame.on_disk && <span className="ml-2 text-amber-400/80">· reconstructed (not on disk)</span>}
        </p>
      </div>

      <Card className="px-5 py-4">
        <SourceBar by_source={blame.summary.by_source} />
      </Card>

      <Card className="overflow-hidden">
        <div className="text-xs text-slate-500 px-4 py-2 border-b border-white/10">blame</div>
        <pre className="text-[13px] leading-[1.55] overflow-x-auto">
          {lines.map((ln, i) => {
            const n = i + 1;
            const s = spanForLine(blame.spans, n);
            const color = s ? sourceMeta(s.source).color : "#334155";
            const edited = s?.is_last_known;
            return (
              <div key={n} className="flex items-stretch hover:bg-white/[0.03]">
                <span className="w-1 shrink-0" style={{ background: color }} />
                <span className="w-10 shrink-0 text-right pr-3 text-slate-600 select-none">{n}</span>
                <code className="flex-1 pr-4 whitespace-pre" style={edited ? { background: "rgba(234,179,8,0.06)" } : undefined}>
                  {ln || " "}
                </code>
              </div>
            );
          })}
        </pre>
      </Card>

      {aiSpans.length > 0 && (
        <Card className="px-5 py-5">
          <SectionTitle>AI contributions</SectionTitle>
          <div className="space-y-3">
            {aiSpans.map((s, i) => (
              <div key={i} className="flex gap-3 text-sm">
                <span className="w-1 rounded-full shrink-0" style={{ background: sourceMeta(s.source).color }} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-300">
                      lines {s.start}–{s.end}
                    </span>
                    <span className="text-cyan-400/90 text-xs">{s.author}</span>
                    <ConfidenceBadge badge={s.badge} />
                    {s.is_last_known && (
                      <span className="text-[11px] text-amber-400">human-edited ~{s.human_edit_lines}ln ({Math.round(s.edit_ratio * 100)}%)</span>
                    )}
                  </div>
                  {s.prompt_excerpt && <div className="text-slate-500 text-xs mt-1 italic">“{s.prompt_excerpt}”</div>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
