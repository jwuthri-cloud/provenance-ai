// Server-side data access for the dashboard.
//
// M4-local: the dashboard reads the LOCAL daemon's analytics API. The daemon
// host/port/token live in TRACE_HOME/daemon.json (written by the daemon). In
// full M4 this same layer points at the cloud sync server instead — same shapes.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

function traceHome(): string {
  return process.env.TRACE_HOME || path.join(os.homedir(), ".trace");
}

function daemonBase(): string | null {
  try {
    const info = JSON.parse(fs.readFileSync(path.join(traceHome(), "daemon.json"), "utf8"));
    return `http://${info.host || "127.0.0.1"}:${info.port}`;
  } catch {
    return null;
  }
}

async function get<T>(p: string): Promise<T | null> {
  const base = daemonBase();
  if (!base) return null;
  try {
    const res = await fetch(base + p, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export type Overview = {
  version: string;
  events: number;
  files: number;
  sessions: number;
  repos: number;
  models: string[];
  chain_head: string | null;
  total_lines: number;
  by_source: Record<string, number>;
  ai_lines: number;
  human_lines: number;
  generated_lines: number;
  ai_pct: number;
  recent: { file: string; source: string; model: string | null; lines: number; ts: string }[];
};

export type FileRow = {
  repo_id: string;
  file: string;
  events: number;
  lines: number;
  by_source: Record<string, number>;
  ai_pct: number;
  top_model: string | null;
  flagged: boolean;
  last_ts: string;
};

export type Span = {
  start: number;
  end: number;
  source: string;
  author: string;
  model: string | null;
  confidence: number;
  badge: string;
  match_kind: string | null;
  is_last_known: boolean;
  prompt_excerpt: string | null;
  edit_ratio: number;
  human_edit_lines: number;
  event_id: string | null;
};

export type Blame = {
  file: string;
  repo_id: string;
  lines: number;
  on_disk: boolean;
  text: string;
  spans: Span[];
  summary: { total_lines: number; by_source: Record<string, number>; pct: Record<string, number>; models: string[] };
};

export type Session = {
  session_id: string;
  model: string | null;
  prompt_excerpt: string | null;
  events: number;
  lines: number;
  files: string[];
  first_ts: string;
  last_ts: string;
};

export type TimelineDay = { day: string; by_source: Record<string, number>; lines: number };

export const getOverview = () => get<Overview>("/api/overview");
export const getFiles = () => get<{ files: FileRow[] }>("/api/files");
export const getSessions = () => get<{ sessions: Session[] }>("/api/sessions");
export const getTimeline = () => get<{ timeline: TimelineDay[] }>("/api/timeline");
export const getFileBlame = (repoId: string, p: string) =>
  get<Blame>(`/api/file?repo_id=${encodeURIComponent(repoId)}&path=${encodeURIComponent(p)}`);

export function daemonConnected(): boolean {
  return daemonBase() !== null;
}
