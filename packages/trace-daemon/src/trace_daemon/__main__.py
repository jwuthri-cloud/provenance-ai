"""`trace-daemon` entrypoint — boot the local engine and serve on 127.0.0.1."""
from __future__ import annotations

import os

from . import config, telemetry
from .hotstore import HotStore
from .server import create_app
from .spool import SpoolDrainer, drain_once
from .vault import Vault


def build_store() -> HotStore:
    config.ensure_home()
    vault = Vault(config.vault_key_path())
    return HotStore(config.db_path(), vault)


def main() -> None:
    import uvicorn

    config.ensure_home()
    host = os.environ.get("TRACE_HOST", "127.0.0.1")
    port = int(os.environ.get("TRACE_PORT", str(config.DEFAULT_PORT)))
    token = config.existing_token() or config.mint_token()

    store = build_store()
    config.write_daemon_info(host, port, token, os.getpid())

    drained = drain_once(store)  # pick up anything captured while we were down
    SpoolDrainer(store).start()
    telemetry.emit("daemon_started")

    app = create_app(store, token)
    print(f"trace daemon v{config.VERSION} on http://{host}:{port}  (db={config.db_path()}, spool_drained={drained})")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
