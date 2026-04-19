from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .config import AppConfig
from .line_patterns import parse_log_line
from .models import IgnoredBlock, LogEntry
from .timeline import apply_timeline
from .wordpress_blocks import iter_blocks


def parse_post_content(
    post_content: str,
    post_date: str,
    config: AppConfig,
    verbose: bool = False,
) -> dict[str, Any]:
    """Parse Gutenberg post content into a stable dictionary payload.

    Canonical return type for now is a dict with JSON-serializable fields:
    - post_date
    - entries
    - ignored_blocks
    - warnings
    """
    entries: list[LogEntry] = []
    ignored_blocks: list[IgnoredBlock] = []

    blocks = iter_blocks(post_content)
    if verbose:
        print(f"[INFO] Extracted Gutenberg blocks: {len(blocks)}")
        print("[INFO] Scanning blocks for timed paragraph entries")

    for block in blocks:
        block_type = block.block_type
        if block_type != "paragraph":
            ignored_blocks.append(
                IgnoredBlock(
                    index=block.index,
                    type=f"wp:{block_type}",
                    reason="unsupported_block_type",
                    raw=block.raw_paragraph_html or "",
                )
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:{block_type} (unsupported block)")
            continue

        visible = (block.visible_text or "").strip()
        if not visible:
            ignored_blocks.append(
                IgnoredBlock(index=block.index, type="wp:paragraph", reason="empty_paragraph", raw=block.raw_paragraph_html or "")
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:paragraph (empty paragraph)")
            continue

        parsed_line = parse_log_line(visible, config)
        if parsed_line is None:
            ignored_blocks.append(
                IgnoredBlock(index=block.index, type="wp:paragraph", reason="no_leading_time", raw=block.raw_paragraph_html or "")
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:paragraph (no leading time)")
            continue

        summary = parsed_line.summary.strip()
        if not summary and not config.allow_empty_summary:
            ignored_blocks.append(
                IgnoredBlock(index=block.index, type="wp:paragraph", reason="empty_summary", raw=block.raw_paragraph_html or "")
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:paragraph (empty summary)")
            continue

        entries.append(
            LogEntry(
                date=post_date,
                start_time=parsed_line.start_time,
                end_time=parsed_line.end_time,
                summary=summary,
                raw=block.raw_paragraph_html or "",
                status="needs_review",
            )
        )
        if verbose:
            print(f"[DEBUG] Accepted entry #{len(entries)}: {parsed_line.start_time} {summary}")

    entries, warnings = apply_timeline(entries, config)

    if verbose:
        print(f"[INFO] Parsed entries: {len(entries)}")
        print(f"[INFO] Ignored blocks: {len(ignored_blocks)}")
        for warn in warnings:
            print(f"[WARN] {warn.message}")

    return {
        "post_date": post_date,
        "entries": [asdict(entry) for entry in entries],
        "ignored_blocks": [asdict(block) for block in ignored_blocks],
        "warnings": [asdict(item) for item in warnings],
    }
