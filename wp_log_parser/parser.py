from __future__ import annotations

from .config import AppConfig
from .line_patterns import parse_log_line
from .models import IgnoredBlock, LogEntry, ParsedPost
from .timeline import apply_timeline
from .wordpress_blocks import iter_blocks


def parse_post_content(
    post_content: str,
    post_date: str,
    config: AppConfig,
    verbose: bool = False,
) -> ParsedPost:
    parsed = ParsedPost(post_date=post_date)
    blocks = iter_blocks(post_content)

    if verbose:
        print(f"[INFO] Extracted Gutenberg blocks: {len(blocks)}")
        print("[INFO] Scanning blocks for timed paragraph entries")

    for block in blocks:
        if block.block_type != "paragraph":
            parsed.ignored_blocks.append(
                IgnoredBlock(index=block.index, type=f"wp:{block.block_type}", reason="unsupported_block_type")
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:{block.block_type} (unsupported block)")
            continue

        if not block.raw_paragraph_html or not block.visible_text:
            parsed.ignored_blocks.append(
                IgnoredBlock(index=block.index, type="wp:paragraph", reason="empty_paragraph")
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:paragraph (empty paragraph)")
            continue

        parsed_line = parse_log_line(block.visible_text, config)
        if not parsed_line:
            parsed.ignored_blocks.append(
                IgnoredBlock(index=block.index, type="wp:paragraph", reason="no_leading_time", raw=block.visible_text)
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:paragraph (no leading time)")
            continue

        if not parsed_line.summary and not config.allow_empty_summary:
            parsed.ignored_blocks.append(
                IgnoredBlock(index=block.index, type="wp:paragraph", reason="empty_summary", raw=block.visible_text)
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{block.index}: wp:paragraph (empty summary)")
            continue

        parsed.entries.append(
            LogEntry(
                date=post_date,
                start_time=parsed_line.start_time,
                end_time=parsed_line.end_time,
                summary=parsed_line.summary,
                raw=block.raw_paragraph_html,
                status="needs_review",
            )
        )
        if verbose:
            print(f"[DEBUG] Accepted entry #{len(parsed.entries)}: {parsed_line.start_time} {parsed_line.summary}")

    parsed.entries, parsed.warnings = apply_timeline(parsed.entries, config)

    if verbose:
        print(f"[INFO] Parsed entries: {len(parsed.entries)}")
        print(f"[INFO] Ignored blocks: {len(parsed.ignored_blocks)}")
        for warn in parsed.warnings:
            print(f"[WARN] {warn.message}")
    return parsed
