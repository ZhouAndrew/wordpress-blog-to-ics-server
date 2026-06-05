from __future__ import annotations

from typing import Any

from .config import AppConfig
from .ics import build_public_ics_url
from .service_mode import export_post_to_ics, publish_once


def publish_post(config: AppConfig, post_id: int, verbose: bool = False) -> dict[str, Any] | None:
    post = fetch_post(config, post_id)
    post_date = normalize_post_date(post.post_date)
    parsed: ParsedPost = parse_post_content(post.post_content, post_date, config, verbose=verbose)
    attach_source_metadata(parsed, post)
    getattr(parsed, "refresh_ics_preview", lambda _timezone: "")(config.timezone)

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
        "post_id": result["post_id"],
        "title": result["title"],
        "post_date": result["post_date"],
        "ics_file": result["ics_file"],
        "ics_url": build_public_ics_url(config.ics_base_url, str(result["ics_file"])),
        "entry_count": result["entry_count"],
        "ignored_block_count": result["ignored_block_count"],
        "warning_count": result["warning_count"],
        "parsed_json_file": str(result.get("parsed_json_file") or ""),
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
            today = today_date_str(config.timezone)
            today_candidates = find_today_ics_candidates(Path(config.output_dir), today)
            selected_today = select_today_ics(today_candidates)
            generate_today_ics(config.output_dir, config.timezone)
            today_source = selected_today.name
            today_refreshed = True
            if verbose:
                print(f"[OK] Selected today source: {today_source}")
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
