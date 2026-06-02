from __future__ import annotations

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
from .ics import build_public_ics_url, generate_ics
from .ics_exporter import (
    write_ignored_blocks,
    write_parsed_post_json,
    write_post_ics,
    write_publish_index,
    write_publish_index_html,
)
from .parser import parse_post_content
from .source_metadata import attach_source_metadata


def _entries_for_export(parsed, mode: str):
    if mode == "include":
        return parsed.entries
    if mode == "skip":
        return [entry for entry in parsed.entries if entry.status != "needs_review"]
    blocked = [entry for entry in parsed.entries if entry.status == "needs_review"]
    if blocked:
        raise RuntimeError(f"Post {getattr(parsed, 'post_id', None) or 'unknown'} has {len(blocked)} entries needing review.")
    return parsed.entries


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [HTTP] {self.address_string()} - {fmt % args}")


def _phase(verbose: bool, stage: str, message: str) -> None:
    if verbose:
        print(f"[PHASE] {stage}: {message}")


def export_post_to_ics(
    config: AppConfig,
    post_id: int,
    verbose: bool = False,
    output_path: str | None = None,
    write_parsed_json: bool = False,
) -> dict[str, Any]:
    """Fetch one WordPress post, parse it, and export its structured events to ICS."""
    _phase(verbose, "fetch", f"fetching WordPress post {post_id}")
    post = fetch_post(config, post_id)

    _phase(verbose, "parse", f"parsing post {post_id}")
    post_date = normalize_post_date(post.post_date)
    parsed = parse_post_content(post.post_content, post_date, config, verbose=verbose)
    attach_source_metadata(parsed, post)
    warnings = list(getattr(parsed, "warnings", []))
    if warnings:
        print(f"[WARN] Timeline warnings: {len(warnings)}")
        for warn in warnings:
            print(f"[WARN] {warn.reason}: {warn.message}")
    if not parsed.entries:
        raise RuntimeError("No valid timed log entries found in post.")

    _phase(verbose, "export", f"exporting post {post_id} to ICS")
    export_entries = _entries_for_export(parsed, config.review_entry_export_mode)
    if output_path:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(generate_ics(export_entries, timezone=config.timezone), encoding="utf-8", newline="")
    else:
        _phase(verbose, "export", f"writing ICS for post {post_id}")
        out_path = Path(write_post_ics(post, export_entries, config.output_dir, config.timezone))
    if verbose:
        print(f"[OK] Wrote ICS file: {out_path}")

    parsed_json_file = None
    if write_parsed_json:
        parsed_json_file = write_parsed_post_json(str(out_path.parent), out_path.name, parsed)
        if verbose:
            print(f"[OK] Wrote parsed JSON: {parsed_json_file}")

    ignored_file = None
    if config.save_ignored_blocks:
        ignored_file = write_ignored_blocks(str(out_path.parent), out_path.name, parsed.ignored_blocks)
        if verbose:
            print(f"[OK] Wrote ignored blocks: {ignored_file}")

    return {
        "post_id": post.post_id,
        "title": post.title,
        "post_date": post.post_date,
        "output_file": str(out_path),
        "ics_file": out_path.name,
        "entry_count": len(export_entries),
        "ignored_block_count": len(parsed.ignored_blocks),
        "warning_count": len(warnings),
        "entries": [getattr(entry, "__dict__", {}) for entry in parsed.entries],
        "ignored_blocks": [getattr(block, "__dict__", {}) for block in parsed.ignored_blocks],
        "parsed_json_file": str(parsed_json_file) if parsed_json_file else None,
        "ignored_file": str(ignored_file) if ignored_file else None,
    }


def update_today_ics(
    config: AppConfig,
    mode: str = "copy",
    post_id: int | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Refresh the today.ics alias from already-published ICS files."""
    _phase(verbose, "publish", "selecting today's published ICS")
    today = today_date_str(config.timezone)
    candidates = find_today_ics_candidates(Path(config.output_dir), today)
    selected = select_today_ics(candidates, post_id)
    target = generate_today_ics(
        config.output_dir,
        config.timezone,
        preferred_post_id=post_id,
        mode=mode,
    )
    if verbose:
        print(f"[OK] Selected today's ICS: {selected.name}")
        print(f"[OK] Updated alias: {target.name}")
    return {
        "today": today,
        "source_file": selected.name,
        "target_file": target.name,
        "mode": mode,
    }


def publish_once(config: AppConfig, days: int, verbose: bool = False) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _phase(verbose, "fetch", f"listing recent WordPress posts from last {days} days")
    post_ids = list_recent_post_ids(config, days)
    items = []
    for post_id in post_ids:
        _phase(verbose, "fetch", f"fetching WordPress post {post_id}")
        post = fetch_post(config, post_id)
        _phase(verbose, "parse", f"parsing post {post_id}")
        post_date = normalize_post_date(post.post_date)
        parsed = parse_post_content(post.post_content, post_date, config, verbose=verbose)
        attach_source_metadata(parsed, post)
        if parsed.warnings and verbose:
            for warn in parsed.warnings:
                print(f"[WARN] post {post_id}: {warn.reason} - {warn.message}")
        if not parsed.entries:
            if verbose:
                print(f"[WARN] Skipped post {post_id}: no valid timed entries")
            continue

        export_entries = _entries_for_export(parsed, config.review_entry_export_mode)
        if not export_entries:
            if verbose:
                print(f"[WARN] Skipped post {post_id}: all entries filtered by review_entry_export_mode={config.review_entry_export_mode}")
            continue
        _phase(verbose, "export", f"writing ICS for post {post_id}")
        out_path = Path(write_post_ics(post, export_entries, config.output_dir, config.timezone))
        if verbose:
            print(f"[OK] Published post {post_id}: {out_path.name}")

        if config.save_ignored_blocks:
            ignored_path = write_ignored_blocks(config.output_dir, out_path.name, parsed.ignored_blocks)
            if verbose:
                print(f"[OK] Wrote ignored blocks: {ignored_path.name}")

        items.append(
            {
                "post_id": post.post_id,
                "title": post.title,
                "post_date": post.post_date,
                "ics_file": out_path.name,
                "ics_url": build_public_ics_url(config.ics_base_url, out_path.name),
                "entry_count": len(export_entries),
                "ignored_block_count": len(parsed.ignored_blocks),
                "warning_count": len(parsed.warnings),
            }
        )

    items.sort(key=lambda x: x["post_date"], reverse=True)
    _phase(verbose, "publish", "writing publish index artifacts")
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
    return result


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
