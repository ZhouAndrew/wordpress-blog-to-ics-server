from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .aliases import find_today_ics_candidates, generate_today_ics, select_today_ics, today_date_str
from .config import AppConfig
from .fetcher import fetch_post, list_recent_post_ids, normalize_post_date
from .ics import build_public_ics_url
from .ics_exporter import (
    write_ignored_blocks,
    write_parsed_post_json,
    write_post_ics,
    write_publish_index,
    write_publish_index_html,
)
from .models import ParsedPost
from .parser import parse_post_content


def publish_post(config: AppConfig, post_id: int, verbose: bool = False) -> dict[str, Any] | None:
    post = fetch_post(config, post_id)
    post_date = normalize_post_date(post.post_date)
    parsed: ParsedPost = parse_post_content(post.post_content, post_date, config, verbose=verbose)
    parsed.post_id = post.post_id
    parsed.source_id = f"wp:{post.post_id}"
    for entry in parsed.entries:
        entry.source_id = parsed.source_id

    if not parsed.entries:
        if verbose:
            print(f"[WARN] Skipped post {post_id}: no valid timed entries")
        return None

    out_path = write_post_ics(post, parsed.entries, config.output_dir, config.timezone)
    if verbose:
        print(f"[OK] Published post {post_id}: {out_path.name}")

    write_parsed_post_json(config.output_dir, out_path.name, parsed)
    if config.save_ignored_blocks:
        ignored_path = write_ignored_blocks(config.output_dir, out_path.name, parsed.ignored_blocks)
        if verbose:
            print(f"[OK] Wrote ignored blocks: {ignored_path.name}")

    return {
        "post_id": post.post_id,
        "title": post.title,
        "post_date": post.post_date,
        "ics_file": out_path.name,
        "ics_url": build_public_ics_url(config.ics_base_url, out_path.name),
        "entry_count": len(parsed.entries),
        "ignored_block_count": len(parsed.ignored_blocks),
        "warning_count": len(parsed.warnings),
        "parsed_json_file": out_path.name.replace(".ics", ".parsed.json"),
    }


def publish_recent(config: AppConfig, days: int, verbose: bool = False) -> dict[str, Any]:
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    post_ids = list_recent_post_ids(config, days)
    items = []
    for post_id in post_ids:
        item = publish_post(config, post_id=post_id, verbose=verbose)
        if item:
            items.append(item)

    items.sort(key=lambda x: x["post_date"], reverse=True)
    index_path = write_publish_index(config.output_dir, items, days)
    html_path = write_publish_index_html(config.output_dir, items)

    today_refreshed = False
    today_source = None
    if items:
        try:
            generate_today_ics(config.output_dir, config.timezone)
            today_candidates = find_today_ics_candidates(Path(config.output_dir), today_date_str(config.timezone))
            today_source = select_today_ics(today_candidates).name
            today_refreshed = True
        except Exception as exc:
            if verbose:
                print(f"[WARN] Could not refresh today.ics automatically: {exc}")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recent_days": days,
        "published_count": len(items),
        "index_json": str(index_path),
        "index_html": str(html_path),
        "today_refreshed": today_refreshed,
        "today_source_file": today_source,
        "items": items,
    }
