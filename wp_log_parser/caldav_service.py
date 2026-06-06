from __future__ import annotations

"""Service boundary that prepares structured CalDAV sync DTOs.

The service owns WordPress reads and parser/exporter orchestration. The sync
engine consumes the returned DTOs and remains focused on CalDAV transport and
index reconciliation.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from .caldav_exporter import (
    CalDAVRenderedEvent,
    canonical_content_hash,
    render_parsed_post_events,
)
from .config import AppConfig
from .fetcher import fetch_post, normalize_post_date
from .parser import parse_post_content
from .source_metadata import attach_source_metadata
from .wordpress import list_post_metadata_paginated, list_posts_rest, list_posts_wpcli


@dataclass(frozen=True)
class CalDAVSyncPost:
    post_id: int
    modified_gmt: str
    content_hash: str | None
    events: list[CalDAVRenderedEvent] | None
    content_changed: bool


@dataclass(frozen=True)
class CalDAVSyncBatch:
    source_post_ids: set[int]
    posts: list[CalDAVSyncPost]


def list_caldav_post_metadata(
    config: AppConfig, per_page: int = 100
) -> list[dict[str, Any]]:
    def _fetch_page(page: int, size: int) -> list[dict[str, str | int]]:
        if config.wordpress_mode == "wpcli":
            return list_posts_wpcli(
                config.wp_path,
                config.wp_cli_path,
                per_page=size,
                limit=None,
                page=page,
            )
        return list_posts_rest(
            config.base_url,
            config.username,
            config.app_password,
            config.verify_ssl,
            per_page=size,
            limit=None,
            page=page,
        )

    posts, _ = list_post_metadata_paginated(fetch_page=_fetch_page, per_page=per_page)
    return [dict(row) for row in posts]


def render_post_events(
    post_id: int, post_date: str, post_content: str, config: AppConfig, uid_domain: str
) -> list[CalDAVRenderedEvent]:
    parsed = parse_post_content(post_content, normalize_post_date(post_date), config)
    attach_source_metadata(parsed, post_id)
    return render_parsed_post_events(
        parsed, post_id=post_id, timezone=config.timezone, uid_domain=uid_domain
    )


def build_caldav_sync_batch(
    config: AppConfig,
    *,
    uid_domain: str,
    previous_posts: Mapping[str, Any],
) -> CalDAVSyncBatch:
    metadata = list_caldav_post_metadata(config)
    post_map = {int(item["id"]): item for item in metadata}
    changed_posts: list[CalDAVSyncPost] = []

    for post_id, meta in post_map.items():
        post_id_key = str(post_id)
        prev = previous_posts.get(post_id_key)
        modified_gmt = str(meta.get("modified_gmt", ""))

        if prev is not None and getattr(prev, "modified_gmt", "") == modified_gmt:
            continue

        post = fetch_post(config, post_id)
        content_hash = canonical_content_hash(post.post_content)
        if prev is not None and getattr(prev, "content_hash", "") == content_hash:
            changed_posts.append(
                CalDAVSyncPost(
                    post_id=post_id,
                    modified_gmt=modified_gmt,
                    content_hash=content_hash,
                    events=None,
                    content_changed=False,
                )
            )
            continue

        changed_posts.append(
            CalDAVSyncPost(
                post_id=post_id,
                modified_gmt=modified_gmt,
                content_hash=content_hash,
                events=render_post_events(
                    post_id, post.post_date, post.post_content, config, uid_domain
                ),
                content_changed=True,
            )
        )

    return CalDAVSyncBatch(source_post_ids=set(post_map), posts=changed_posts)
