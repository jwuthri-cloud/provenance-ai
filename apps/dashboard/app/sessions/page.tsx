import { Card, DaemonDown } from "../../components/ui";
import { fmtTime } from "../../lib/format";
import { getSessions } from "../../lib/trace";

export const dynamic = "force-dynamic";

export default async function SessionsPage() {
  const data = await getSessions();
  if (!data) return <DaemonDown />;
  const sessions = data.sessions;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Sessions</h1>
        <p className="text-sm text-slate-500">
          {sessions.length} capture session{sessions.length === 1 ? "" : "s"} · prompt → what it produced
        </p>
      </div>

      {sessions.length === 0 && <Card className="px-6 py-10 text-center text-slate-400">No sessions captured yet.</Card>}

      <div className="space-y-3">
        {sessions.map((s) => (
          <Card key={s.session_id} className="px-5 py-4">
            <div className="flex items-center gap-2 flex-wrap">
              {s.model && <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300">{s.model}</span>}
              <span className="text-xs text-slate-500 font-mono">{s.session_id}</span>
              <span className="ml-auto text-xs text-slate-500">{fmtTime(s.first_ts)}</span>
            </div>
            {s.prompt_excerpt && (
              <div className="text-slate-200 mt-2.5 italic">“{s.prompt_excerpt}”</div>
            )}
            <div className="flex items-center gap-3 mt-3 text-xs text-slate-500">
              <span className="text-slate-300">{s.lines} lines</span>
              <span>·</span>
              <span>{s.events} events</span>
              <span>·</span>
              <span className="truncate">{s.files.join(", ")}</span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
