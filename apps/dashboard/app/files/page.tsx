import Link from "next/link";

import { Card, DaemonDown, Flag, SourceBar } from "../../components/ui";
import { fmtTime } from "../../lib/format";
import { getFiles } from "../../lib/trace";

export const dynamic = "force-dynamic";

export default async function FilesPage() {
  const data = await getFiles();
  if (!data) return <DaemonDown />;
  const files = data.files;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Files</h1>
        <p className="text-sm text-slate-500">{files.length} files with recorded provenance, most AI-authored first</p>
      </div>

      {files.length === 0 && <Card className="px-6 py-10 text-center text-slate-400">No files captured yet.</Card>}

      <div className="space-y-2.5">
        {files.map((f) => (
          <Link key={f.repo_id + f.file} href={`/files/view?repo_id=${encodeURIComponent(f.repo_id)}&path=${encodeURIComponent(f.file)}`}>
            <Card className="px-5 py-4 hover:border-white/20 transition-colors">
              <div className="flex items-center gap-3 mb-2.5">
                <span className="font-mono text-sm text-slate-100 truncate">{f.file}</span>
                {f.flagged && <Flag />}
                <span className="ml-auto text-sm font-semibold text-white">{f.ai_pct}%</span>
                <span className="text-xs text-slate-500">AI</span>
              </div>
              <SourceBar by_source={f.by_source} height={8} />
              <div className="flex items-center gap-3 mt-3 text-xs text-slate-500">
                <span>{f.lines} lines</span>
                <span>·</span>
                <span>{f.events} events</span>
                {f.top_model && <><span>·</span><span className="text-cyan-400/80">{f.top_model}</span></>}
                <span className="ml-auto">{fmtTime(f.last_ts)}</span>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
