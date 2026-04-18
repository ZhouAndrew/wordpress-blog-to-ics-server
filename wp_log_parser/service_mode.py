from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from .aliases import find_today_ics_candidates, generate_today_ics, select_today_ics, today_date_str
from .config import AppConfig
from .fetcher import fetch_post, list_recent_post_ids, normalize_post_date
from .ics import build_public_ics_url
from .ics_exporter import (
    write_ignored_blocks,
    write_post_ics,
    write_publish_index,
    write_publish_index_html,
)
from .parser import parse_post_content


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [HTTP] {self.address_string()} - {fmt % args}")


def publish_once(config: AppConfig, days: int, verbose: bool = False) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    post_ids = list_recent_post_ids(config, days)
    items = []
    for post_id in post_ids:
        post = fetch_post(config, post_id)
        post_date = normalize_post_date(post.post_date)
        parsed = parse_post_content(post.post_content, post_date, config, verbose=verbose)
        if not parsed["entries"]:
            if verbose:
                print(f"[WARN] Skipped post {post_id}: no valid timed entries")
            continue

        out_path = write_post_ics(post, parsed["entries"], config.output_dir, config.timezone)
        if verbose:
            print(f"[OK] Published post {post_id}: {out_path.name}")

        if config.save_ignored_blocks:
            ignored_path = write_ignored_blocks(config.output_dir, out_path.name, parsed["ignored_blocks"])
            if verbose:
                print(f"[OK] Wrote ignored blocks: {ignored_path.name}")

        items.append(
            {
                "post_id": post.post_id,
                "title": post.title,
                "post_date": post.post_date,
                "ics_file": out_path.name,
                "ics_url": build_public_ics_url(config.ics_base_url, out_path.name),
                "entry_count": len(parsed["entries"]),
                "ignored_block_count": len(parsed["ignored_blocks"]),
            }
        )

    items.sort(key=lambda x: x["post_date"], reverse=True)
    index_path = write_publish_index(config.output_dir, items, days)
    html_path = write_publish_index_html(config.output_dir, items)

    today_refreshed = False
    today_source = None
    if items:
        try:
            today_target = generate_today_ics(config.output_dir, config.timezone)
            today_candidates = find_today_ics_candidates(Path(config.output_dir), today_date_str(config.timezone))
            today_source = select_today_ics(today_candidates).name
            today_refreshed = True
            if verbose:
                print(f"[OK] Refreshed today alias: {today_target.name}")
        except Exception as exc:
            if verbose:
                print(f"[WARN] Could not refresh today.ics automatically: {exc}")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recent_days": days,
        "published_count": len(items),
        "index_json": str(index_path),
        "index_html": str(html_path),
        "today_refreshed": today_refreshed,
        "today_source_file": today_source,
        "items": items,
    }
    if verbose:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def start_http_server(directory: str, host: str, port: int) -> ThreadingHTTPServer:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    handler = partial(QuietHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer((host, port), handler)
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

    server = start_http_server(config.output_dir, host, port)
    print(f"[OK] Serving {config.output_dir} at http://{host}:{port}/")

    try:
        while True:
            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[INFO] Publish cycle started at {started_at}")
            try:
                publish_once(config, days=days, verbose=verbose)
                print("[OK] Publish cycle completed")
            except Exception as exc:
                print(f"[ERROR] Publish cycle failed: {exc}")
            print(f"[INFO] Sleeping {interval_seconds}s before next cycle")
            time.sleep(interval_seconds)
    finally:
        server.shutdown()
        server.server_close()
