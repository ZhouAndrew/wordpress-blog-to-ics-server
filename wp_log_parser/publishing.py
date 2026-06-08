from __future__ import annotations

"""Public publishing helpers for compatibility with older integrations.

The canonical batch publishing implementation lives in
:mod:`wp_log_parser.service_mode`.  This module remains public as a small
facade for callers that imported ``wp_log_parser.publishing`` directly while
still routing work through the same source → parser → exporter pipeline.
"""

from pathlib import Path
from typing import Any

from .config import AppConfig
from .fetcher import fetch_post, normalize_post_date
from .ics import build_public_ics_url
from .ics_exporter import write_ignored_blocks, write_parsed_post_json, write_post_ics
from .models import ParsedPost
from .parser import parse_post_content
from .service_mode import _entries_for_export, publish_once as _publish_once
from .source_metadata import attach_source_metadata


def publish_post(config: AppConfig, post_id: int, verbose: bool = False) -> dict[str, Any] | None:
    """Publish one WordPress post to ICS and sidecar JSON artifacts.

    Returns a publish-index-compatible item dictionary, or ``None`` when the
    post has no exportable timed entries.
    """
    post = fetch_post(config, post_id)
    post_date = normalize_post_date(post.post_date)
    parsed: ParsedPost = parse_post_content(post.post_content, post_date, config, verbose=verbose)
    attach_source_metadata(parsed, post)
    getattr(parsed, "refresh_ics_preview", lambda _timezone: "")(config.timezone)

    warnings = list(getattr(parsed, "warnings", []))
    if warnings and verbose:
        for warn in warnings:
            print(f"[WARN] post {post_id}: {warn.reason} - {warn.message}")

    if not parsed.entries:
        if verbose:
            print(f"[WARN] Skipped post {post_id}: no valid timed entries")
        return None

    export_entries = _entries_for_export(parsed, config.review_entry_export_mode)
    if not export_entries:
        if verbose:
            print(
                f"[WARN] Skipped post {post_id}: "
                f"all entries filtered by review_entry_export_mode={config.review_entry_export_mode}"
            )
        return None

    out_path = Path(write_post_ics(post, export_entries, config.output_dir, config.timezone))
    if verbose:
        print(f"[OK] Published post {post_id}: {out_path.name}")

    parsed_json_path = write_parsed_post_json(config.output_dir, out_path.name, parsed)
    if verbose:
        print(f"[OK] Wrote parsed JSON: {parsed_json_path.name}")

    ignored_path = None
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
        "entry_count": len(export_entries),
        "ignored_block_count": len(parsed.ignored_blocks),
        "warning_count": len(warnings),
        "parsed_json_file": str(parsed_json_path),
        "ignored_file": str(ignored_path) if ignored_path else None,
    }


def publish_recent(config: AppConfig, days: int, verbose: bool = False) -> dict[str, Any]:
    """Publish recent posts using the canonical service-mode implementation."""
    return _publish_once(config, days=days, verbose=verbose)
