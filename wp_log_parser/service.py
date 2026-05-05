from __future__ import annotations

from .config import AppConfig
from .fetcher import PostData, fetch_post as fetch_post_data, fetch_today_post, normalize_post_date
from .ics import generate_ics
from .parser import parse_post_content
from .source_metadata import attach_source_metadata
from .wordpress import (
    list_posts_rest,
    list_posts_wpcli,
    sort_and_limit_posts,
)


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


def fetch_post(config: AppConfig, post_id: int | None = None) -> PostData:
    """Compatibility wrapper around the canonical structured fetch path."""
    if post_id is None:
        return fetch_today_post(config)
    return fetch_post_data(config, post_id)


def run_today_pipeline(config: AppConfig) -> dict:
    post = fetch_today_post(config)
    parsed = parse_post_content(post.post_content, normalize_post_date(post.post_date), config)
    attach_source_metadata(parsed, post)
    payload = parsed.to_dict(include_ignored=config.save_ignored_blocks)
    payload["ics_preview"] = generate_ics(payload["entries"], timezone=config.timezone)
    return payload
