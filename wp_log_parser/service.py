from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .aliases import find_today_ics_candidates, generate_today_ics, select_today_ics, today_date_str
from .config import AppConfig
from .fetcher import PostData, fetch_post as fetch_post_data, fetch_today_post, normalize_post_date
from .ics import generate_ics
from .ics_exporter import write_post_ics
from .models import LogEntry, ParsedPost
from .parser import parse_post_content
from .source_metadata import attach_source_metadata
from .timeline import apply_timeline
from .validators import validate_output_dir_writable
from .wordpress import (
    list_posts_rest,
    list_posts_wpcli,
)
from .service_mode import export_post_to_ics, publish_once, run_service_loop, update_today_ics


class NoTimedEntriesError(RuntimeError):
    """Raised when a post parses successfully but has no timed log entries."""

    def __init__(self, post: PostData, parsed: ParsedPost) -> None:
        super().__init__("No valid timed log entries found in post.")
        self.post = post
        self.parsed = parsed


def _entries_for_export(entries: list[LogEntry], mode: str, *, context: str = "entries") -> list[LogEntry]:
    if mode == "include":
        return entries
    if mode == "skip":
        return [entry for entry in entries if entry.status != "needs_review"]
    blocked = [entry for entry in entries if entry.status == "needs_review"]
    if blocked:
        raise RuntimeError(f"Refusing to export {len(blocked)} {context} with status=needs_review.")
    return entries


def list_posts(config: AppConfig, per_page: int | None = None) -> list[dict[str, str | int]]:
    per_page = config.post_selection_count if per_page is None else per_page
    if config.wordpress_mode == "wpcli":
        posts = list_posts_wpcli(config.wp_path, config.wp_cli_path, per_page=per_page, limit=per_page)
    else:
        posts = list_posts_rest(
            config.base_url,
            config.username,
            config.app_password,
            config.verify_ssl,
            per_page=per_page,
            limit=per_page,
        )
    return posts


def list_recent_posts(config: AppConfig, days: int, per_page: int = 200) -> list[dict[str, str | int]]:
    """List recent WordPress post metadata without fetching post content."""
    try:
        tz = ZoneInfo(config.timezone)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {config.timezone}") from exc
    cutoff = datetime.now(tz) - timedelta(days=days)
    rows = list_posts(config, per_page=per_page)
    recent: list[dict[str, str | int]] = []
    for row in rows:
        raw_date = str(row.get("date", ""))
        try:
            dt = datetime.fromisoformat(raw_date)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw_date, fmt)
                    break
                except ValueError:
                    dt = datetime.min
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        if dt >= cutoff:
            recent.append(row)
    return sort_and_limit_posts(recent)


def fetch_post(config: AppConfig, post_id: int | None = None) -> PostData:
    """Compatibility wrapper around the canonical structured fetch path."""
    if post_id is None:
        return fetch_today_post(config)
    return fetch_post_data(config, post_id)


def fetch_post_payload(config: AppConfig, post_id: int) -> dict[str, Any]:
    post = fetch_post(config, post_id)
    return {"post_id": post.post_id, "post_content": post.post_content}


def parse_post(config: AppConfig, post_id: int, *, verbose: bool = False) -> ParsedPost:
    post = fetch_post(config, post_id)
    parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config, verbose=verbose)
    attach_source_metadata(parsed, post)
    return parsed


def _log_entries_from_dicts(entries: list[dict[str, Any]]) -> list[LogEntry]:
    return [
        LogEntry(
            date=item["date"],
            start_time=item["start_time"],
            end_time=item.get("end_time"),
            summary=item.get("summary", ""),
            raw=item.get("raw", ""),
            status=item.get("status", "needs_review"),
            source_id=item.get("source_id"),
            start_dt=datetime.fromisoformat(item["start_dt"]) if item.get("start_dt") else None,
            end_dt=datetime.fromisoformat(item["end_dt"]) if item.get("end_dt") else None,
        )
        for item in entries
    ]


def export_ics_from_entries(config: AppConfig, entries: list[dict[str, Any]]) -> str:
    normalized_entries = entries
    if normalized_entries and any(not item.get("start_dt") for item in normalized_entries):
        timeline_entries, _ = apply_timeline(
            [
                LogEntry(
                    date=item["date"],
                    start_time=item["start_time"],
                    end_time=item.get("end_time"),
                    summary=item.get("summary", ""),
                    raw=item.get("raw", ""),
                    status=item.get("status", "needs_review"),
                    source_id=item.get("source_id"),
                )
                for item in normalized_entries
            ],
            config,
        )
        normalized_entries = [entry.to_dict() for entry in timeline_entries]
    typed_entries = _log_entries_from_dicts(normalized_entries)
    export_entries = _entries_for_export(typed_entries, config.review_entry_export_mode)
    return generate_ics(export_entries, timezone=config.timezone)


def export_ics_from_json_file(config: AppConfig, entries_json_path: str | Path) -> str:
    entries = json.loads(Path(entries_json_path).read_text(encoding="utf-8"))
    return export_ics_from_entries(config, entries)


def post_to_ics(config: AppConfig, post_id: int, *, verbose: bool = False) -> dict[str, Any]:
    post = fetch_post(config, post_id)
    parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config, verbose=verbose)
    attach_source_metadata(parsed, post)
    if not parsed.entries:
        raise NoTimedEntriesError(post, parsed)
    export_entries = _entries_for_export(parsed.entries, config.review_entry_export_mode)
    out_path = write_post_ics(post, export_entries, config.output_dir, config.timezone)
    return {
        "post_id": post.post_id,
        "title": post.title,
        "post_date": post.post_date,
        "output_file": str(out_path),
        "entry_count": len(export_entries),
        "ignored_block_count": len(parsed.ignored_blocks),
        "warning_count": len(parsed.warnings),
        "warnings": [warning.to_dict() for warning in parsed.warnings],
        "parsed_entry_count": len(parsed.entries),
    }


def publish_ics(config: AppConfig, *, days: int, verbose: bool = False) -> dict[str, Any]:
    from .service_mode import publish_once

    for path in (config.output_dir, config.error_dir, config.logs_dir):
        dir_check = validate_output_dir_writable(path)
        if not dir_check.ok:
            raise RuntimeError(f"{dir_check.name}: {dir_check.message}")
    return publish_once(config, days=days, verbose=verbose)


def update_today_ics(config: AppConfig, *, post_id: int | None = None, mode: str = "copy") -> dict[str, Any]:
    today = today_date_str(config.timezone)
    candidates = find_today_ics_candidates(Path(config.output_dir), today)
    selected = select_today_ics(candidates, post_id)
    target = generate_today_ics(config.output_dir, config.timezone, preferred_post_id=post_id, mode=mode)
    return {
        "today": today,
        "source_file": selected.name,
        "target_file": target.name,
        "mode": mode,
    }


def run_ics_service(
    config: AppConfig,
    *,
    days: int,
    interval_seconds: int,
    host: str,
    port: int,
    verbose: bool = False,
) -> None:
    from .service_mode import run_service_loop

    run_service_loop(
        config=config,
        days=days,
        interval_seconds=interval_seconds,
        host=host,
        port=port,
        verbose=verbose,
    )


def run_today_pipeline(config: AppConfig) -> dict[str, Any]:
    post = fetch_today_post(config)
    parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config)
    attach_source_metadata(parsed, post)
    getattr(parsed, "refresh_ics_preview", lambda _timezone: "")(config.timezone)
    return parsed.to_dict(include_ignored=config.save_ignored_blocks)
