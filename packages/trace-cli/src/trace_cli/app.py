"""The `trace` CLI app (Typer)."""
from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from trace_daemon import config, repoid, telemetry
from trace_daemon.vault import Vault

from . import provenance, render

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="trace — git-native AI authorship provenance")


@app.command()
def init(
    global_: bool = typer.Option(False, "--global", help="install hooks into ~/.claude instead of ./.claude"),
) -> None:
    """Set up the trace home + token, and wire Claude Code hooks (project-local by default)."""
    config.ensure_home()
    Vault(config.vault_key_path())  # generate the at-rest key if absent
    token = config.existing_token() or config.mint_token()
    info = config.load_daemon_info() or {}
    config.write_daemon_info(info.get("host", "127.0.0.1"),
                             int(info.get("port", config.DEFAULT_PORT)), token, int(info.get("pid", 0)))

    from trace_capture_claude_code.install import merge_into_settings

    settings_path = (Path.home() / ".claude" / "settings.json") if global_ \
        else (Path.cwd() / ".claude" / "settings.json")
    res = merge_into_settings(settings_path)
    render.init_report(res, config.trace_home())
    telemetry.emit("init", command="init")


@app.command()
def status() -> None:
    """Show daemon state, event counts, repo identity, and chain head."""
    store = provenance.open_store()
    try:
        st = store.status()
        st["version"] = config.VERSION
        st["db"] = str(store.db_path)
    finally:
        store.close()
    render.status_report(st, provenance.daemon_health(), repoid.repo_id(Path.cwd()),
                         config.telemetry_enabled())


@app.command()
def blame(
    file: str = typer.Argument(..., help="file to show AI/human authorship for"),
    range_opt: str = typer.Option(None, "--range", help="restrict to lines L1:L2"),
    show_prompts: bool = typer.Option(False, "--show-prompts", help="show full prompt excerpts"),
    json_out: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """git blame, but it tells you which AI wrote each line, from which prompt."""
    abspath = Path(file).expanduser().resolve()
    if not abspath.exists():
        typer.echo(f"no such file: {file}", err=True)
        raise typer.Exit(1)
    range_filter = None
    if range_opt:
        try:
            a, b = range_opt.split(":")
            range_filter = (int(a), int(b))
        except ValueError:
            typer.echo("--range must look like L1:L2", err=True)
            raise typer.Exit(1)
    result = provenance.blame_file(abspath, range_filter)
    if json_out:
        typer.echo(_json.dumps(result, indent=2))
    else:
        render.blame_report(result, show_prompts=show_prompts)
    telemetry.emit("blame_run", command="blame")


@app.command()
def summary(path: str = typer.Option(".", "--path", help="repo path")) -> None:
    """Authorship breakdown for the whole repo (M1: across all captured events)."""
    s = provenance.repo_summary(Path(path).expanduser().resolve())
    render.summary_report(s)


@app.command()
def doctor() -> None:
    """Diagnose the local setup."""
    home = config.trace_home()
    health = provenance.daemon_health()
    checks = [
        ("trace home", home.exists(), str(home)),
        ("hot store", config.db_path().exists(), str(config.db_path())),
        ("vault key", config.vault_key_path().exists(), "prompt encryption key present"),
        ("daemon token", bool(config.existing_token()), "ingest auth token configured"),
        ("daemon running", health is not None, "needed for live capture"),
        ("git repo", repoid.repo_root(Path.cwd()) is not None, "for commit/notes (M2)"),
        ("claude hooks", (Path.cwd() / ".claude" / "settings.json").exists(),
         "run `trace init` to install"),
    ]
    render.doctor_report(checks)


@app.command()
def daemon() -> None:
    """Run the local daemon in the foreground (Ctrl-C to stop)."""
    from trace_daemon.__main__ import main as daemon_main

    daemon_main()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
