from __future__ import annotations

import time
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from .config import AppConfig
from .publishing import publish_recent


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [HTTP] {self.address_string()} - {fmt % args}")


def publish_once(config: AppConfig, days: int, verbose: bool = False) -> dict[str, Any]:
    return publish_recent(config=config, days=days, verbose=verbose)


def start_http_server(directory: str, host: str, port: int) -> ThreadingHTTPServer:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    handler = partial(QuietHTTPRequestHandler, directory=str(root))
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise RuntimeError(f"Failed to bind HTTP server at {host}:{port}: {exc}") from exc
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_service_loop(
    config: AppConfig,
    days: int,
    interval_seconds: int,
    host: str,
    port: int,
    verbose: bool = False,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("--interval must be > 0")

    print("[INFO] Running initial publish cycle")
    try:
        publish_once(config, days=days, verbose=verbose)
        print("[OK] Initial publish cycle completed")
    except Exception as exc:
        print(f"[ERROR] Initial publish cycle failed: {exc}")

    server = start_http_server(config.output_dir, host, port)
    print(f"[OK] Serving {config.output_dir} at http://{host}:{port}/")

    try:
        next_cycle_at = time.monotonic() + interval_seconds
        while True:
            now = time.monotonic()
            sleep_for = max(0.0, next_cycle_at - now)
            print(f"[INFO] Sleeping {sleep_for:.1f}s before next cycle")
            time.sleep(sleep_for)

            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Publish cycle started at {started_at}")
            try:
                publish_once(config, days=days, verbose=verbose)
                print("[OK] Publish cycle completed")
            except Exception as exc:
                print(f"[ERROR] Publish cycle failed: {exc}")
            next_cycle_at += interval_seconds
    finally:
        server.shutdown()
        server.server_close()
