from __future__ import annotations

from typing import Any

from .config import AppConfig
from .ics import build_public_ics_url
from .service_mode import export_post_to_ics, publish_once


def publish_post(config: AppConfig, post_id: int, verbose: bool = False) -> dict[str, Any] | None:
    """Compatibility wrapper for publishing one post through the service layer."""
    try:
        result = export_post_to_ics(config, post_id=post_id, verbose=verbose, write_parsed_json=True)
    except RuntimeError as exc:
        if "No valid timed log entries" in str(exc):
            if verbose:
                print(f"[WARN] Skipped post {post_id}: no valid timed entries")
            return None
        raise
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
    """Compatibility wrapper for the canonical publish-ICS service flow."""
    return publish_once(config, days=days, verbose=verbose)
