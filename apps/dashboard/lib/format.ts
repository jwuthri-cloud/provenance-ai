// Source palette + helpers, shared across the dashboard.

export const SOURCE_META: Record<string, { label: string; color: string }> = {
  claude_code_tool_call: { label: "Claude Code", color: "#22d3ee" },
  cursor_agent: { label: "Cursor agent", color: "#a78bfa" },
  cursor_autocomplete: { label: "Cursor autocomplete", color: "#8b5cf6" },
  copilot_completion: { label: "Copilot", color: "#34d399" },
  copilot_agent: { label: "Copilot agent", color: "#10b981" },
  zed_agent: { label: "Zed agent", color: "#f472b6" },
  ai_paste: { label: "AI paste", color: "#2dd4bf" },
  inferred: { label: "Inferred", color: "#64748b" },
  human_keyboard: { label: "You (keyboard)", color: "#94a3b8" },
  human_paste: { label: "You (paste)", color: "#cbd5e1" },
  generated: { label: "Generated", color: "#f59e0b" },
};

export function sourceMeta(s: string) {
  return SOURCE_META[s] ?? { label: s, color: "#64748b" };
}

export const AI_SOURCES = new Set([
  "claude_code_tool_call", "cursor_agent", "cursor_autocomplete",
  "copilot_completion", "copilot_agent", "zed_agent", "ai_paste", "inferred",
]);
export const HUMAN_SOURCES = new Set(["human_keyboard", "human_paste"]);
export const GENERATED_SOURCES = new Set(["generated"]);

export function badgeColor(b: string): string {
  if (b === "attributed") return "#22c55e";
  if (b === "approximate") return "#eab308";
  return "#6b7280";
}

export function splitByCategory(by: Record<string, number>) {
  let ai = 0, human = 0, generated = 0;
  for (const [s, n] of Object.entries(by)) {
    if (AI_SOURCES.has(s)) ai += n;
    else if (HUMAN_SOURCES.has(s)) human += n;
    else if (GENERATED_SOURCES.has(s)) generated += n;
  }
  return { ai, human, generated };
}

export function fmtTime(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return s;
  }
}

export function fmtDay(s?: string): string {
  if (!s) return "";
  try {
    return new Date(s + "T00:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return s;
  }
}

export function shortHash(h?: string | null): string {
  return h ? h.slice(0, 12) + "…" : "—";
}
