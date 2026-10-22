"""Terminal rendering for the trace CLI (Rich)."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

_BADGE_STYLE = {"attributed": "green", "approximate": "yellow", "unattributed": "dim"}


def _author_style(source: str) -> str:
    if source.startswith("human") or source == "human_keyboard":
        return "white"
    if source == "generated":
        return "magenta"
    return "cyan"


def blame_report(result: dict, show_prompts: bool = False) -> None:
    file = result.get("file", "?")
    console.print(f"[bold]{file}[/bold]  [dim]({result.get('event_count', 0)} events, "
                  f"{result.get('lines', 0)} lines)[/dim]")
    if not result["spans"]:
        console.print("  [dim]no provenance recorded for this file yet[/dim]")
        return
    for s in result["spans"]:
        rng = f"{s['start']}-{s['end']}" if s["start"] != s["end"] else f"{s['start']}"
        author = f"[{_author_style(s['source'])}]{s['author']}[/]"
        badge = f"[{_BADGE_STYLE.get(s['badge'], 'white')}]{s['badge']}[/]"
        line = f"  [dim]{rng:>9}[/dim]  {author:<46}  {badge}"
        if s.get("edit_ratio"):
            pct = round(s["edit_ratio"] * 100)
            line += f"  [yellow]· human-edited ~{s['human_edit_lines']}ln ({pct}%)[/yellow]"
        console.print(line)
        if show_prompts and s.get("prompt_excerpt"):
            console.print(f"             [dim]prompt:[/dim] \"{s['prompt_excerpt']}\"")
        elif s.get("prompt_excerpt"):
            excerpt = s["prompt_excerpt"]
            short = (excerpt[:60] + "…") if len(excerpt) > 60 else excerpt
            console.print(f"             [dim]prompt: \"{short}\"[/dim]")

    _summary_line(result.get("summary", {}))


def _summary_line(summary: dict) -> None:
    if not summary or not summary.get("by_source"):
        return
    parts = [f"{k} {v}%" for k, v in sorted(summary["pct"].items(), key=lambda kv: -kv[1])]
    console.print(f"  [dim]── {summary['total_lines']} lines: " + ", ".join(parts) + "[/dim]")


def summary_report(s: dict) -> None:
    console.print(f"[bold]repo[/bold]   {s['repo_id']}  [dim](branch: {s.get('branch') or '?'})[/dim]")
    console.print(f"events {s['events']}   sessions {s['sessions']}   lines {s['total_lines']}")
    if s["by_source"]:
        table = Table(show_header=True, header_style="bold")
        table.add_column("source")
        table.add_column("lines", justify="right")
        table.add_column("%", justify="right")
        for src, n in sorted(s["by_source"].items(), key=lambda kv: -kv[1]):
            table.add_row(src, str(n), f"{s['pct'].get(src, 0)}")
        console.print(table)
    if s["models"]:
        console.print(f"models: [cyan]{', '.join(s['models'])}[/cyan]")


def status_report(st: dict, health: dict | None, repo_id: str, telemetry: bool) -> None:
    daemon = "[green]running[/green]" if health else "[yellow]not running[/yellow] (ingest paused; blame still works)"
    console.print(f"[bold]trace[/bold] v{st.get('version', '?')}")
    console.print(f"daemon:    {daemon}")
    console.print(f"db:        {st.get('db')}")
    console.print(f"events:    {st.get('events', 0)}  ·  files {st.get('files', 0)}  ·  "
                  f"sessions {st.get('sessions', 0)}  ·  repos {st.get('repos', 0)}")
    if st.get("by_source"):
        parts = ", ".join(f"{k} {v}" for k, v in st["by_source"].items())
        console.print(f"by source: {parts}")
    if st.get("models"):
        console.print(f"models:    [cyan]{', '.join(st['models'])}[/cyan]")
    console.print(f"repo here: {repo_id}")
    console.print(f"telemetry: {'on' if telemetry else 'off (local-first default)'}")
    head = st.get("chain_head")
    console.print(f"chain:     {head[:16] + '…' if head else '(empty)'}")


def init_report(res: dict, home: Path) -> None:
    console.print(f"[green]✓[/green] trace home ready at [bold]{home}[/bold]")
    if res["added"]:
        console.print(f"[green]✓[/green] Claude Code hooks installed ({', '.join(res['added'])}) "
                      f"→ {res['path']}")
    if res["already"]:
        console.print(f"[dim]· hooks already present ({', '.join(res['already'])})[/dim]")
    console.print("\nNext:")
    console.print("  1. start the daemon:   [bold]trace daemon[/bold]   (in another terminal)")
    console.print("  2. let Claude Code edit files in this repo")
    console.print("  3. see authorship:     [bold]trace blame <file>[/bold]")


def doctor_report(checks: list[tuple[str, bool, str]]) -> None:
    console.print("[bold]trace doctor[/bold]")
    for name, ok, detail in checks:
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {mark} {name:<22} [dim]{detail}[/dim]")
