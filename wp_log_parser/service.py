from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import AppConfig
from .fetcher import PostData, fetch_post as fetch_post_data, fetch_today_post, normalize_post_date
from .parser import parse_post_content
from .source_metadata import attach_source_metadata
from .wordpress import (
    list_posts_rest,
    list_posts_wpcli,
    sort_and_limit_posts,
)
from .service_mode import export_post_to_ics, publish_once, publish_post, run_service_loop, update_today_ics


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


def run_today_pipeline(config: AppConfig) -> dict[str, Any]:
    post = fetch_today_post(config)
    parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config)
    attach_source_metadata(parsed, post)
    getattr(parsed, "refresh_ics_preview", lambda _timezone: "")(config.timezone)
    return parsed.to_dict(include_ignored=config.save_ignored_blocks)
