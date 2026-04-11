from __future__ import annotations

from typing import Any

from .config import AppConfig
from .extractor import TIME_RE, extract_blocks, paragraph_from_block, strip_tags
from .models import LogEntry
from .rules import apply_event_timing_rules, normalize_time


def parse_post_content(post_content: str, post_date: str, config: AppConfig) -> dict[str, Any]:
    entries: list[LogEntry] = []
    ignored_blocks: list[dict[str, str]] = []

    for block_type, block_body in extract_blocks(post_content):
        raw_p = paragraph_from_block(block_body)
        if block_type != "paragraph" or not raw_p:
            ignored_blocks.append({"type": f"wp:{block_type}", "reason": "not a paragraph or no valid time"})
            continue

        visible = strip_tags(raw_p)
        time_match = TIME_RE.match(visible)
        if not time_match:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "not a paragraph or no valid time"})
            continue

        normalized = normalize_time(time_match.group(1), time_match.group(2))
        if normalized is None:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "not a paragraph or no valid time"})
            continue

        summary = time_match.group(3).strip()
        if not summary and not config.allow_empty_summary:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "empty summary disallowed"})
            continue

        entries.append(
            LogEntry(
                date=post_date,
                start_time=normalized,
                end_time=None,
                summary=summary,
                raw=raw_p,
                status="needs_review",
            )
        )

    entries = apply_event_timing_rules(
        entries,
        default_last_event_minutes=config.default_last_event_minutes,
        auto_cross_midnight=config.auto_cross_midnight,
    )

    return {
        "entries": [entry.__dict__ for entry in entries],
        "ignored_blocks": ignored_blocks if config.save_ignored_blocks else [],
    }
