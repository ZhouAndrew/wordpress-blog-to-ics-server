from __future__ import annotations

from datetime import date

from .config import AppConfig
from .ics import generate_ics
from .parser import parse_post_content
from .wordpress import (
    fetch_post_content_rest,
    fetch_post_content_wpcli,
    find_today_post_id_rest,
    find_today_post_id_wpcli,
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


def fetch_post(config: AppConfig, post_id: int | None = None) -> tuple[int, str]:
    resolved_id = post_id
    if config.wordpress_mode == "wpcli":
        if resolved_id is None:
            resolved_id = find_today_post_id_wpcli(config.wp_path, config.wp_cli_path)
        content = fetch_post_content_wpcli(resolved_id, config.wp_path, config.wp_cli_path)
    else:
        if resolved_id is None:
            resolved_id = find_today_post_id_rest(config.base_url, config.username, config.app_password, config.verify_ssl)
        content = fetch_post_content_rest(
            config.base_url,
            resolved_id,
            config.username,
            config.app_password,
            config.verify_ssl,
        )
    return resolved_id, content


def run_today_pipeline(config: AppConfig) -> dict:
    post_id, post_content = fetch_post(config, None)
    parsed = parse_post_content(post_content, date.today().isoformat(), config)
    parsed["ics_preview"] = generate_ics(parsed["entries"], timezone=config.timezone)
    parsed["post_id"] = post_id
    return parsed
