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

def parse_post_content(
    post_content: str,
    post_date: str,
    config: AppConfig,
    verbose: bool = False,
) -> dict[str, Any]:
    entries: list[LogEntry] = []
    ignored_blocks: list[dict[str, str]] = []
    blocks = extract_blocks(post_content)

    if verbose:
        print(f"[INFO] Extracted Gutenberg blocks: {len(blocks)}")
        print("[INFO] Scanning blocks for timed paragraph entries")

    for index, (block_type, block_body) in enumerate(blocks, start=1):
        raw_p = paragraph_from_block(block_body)
        if block_type != "paragraph":
            ignored_blocks.append({"type": f"wp:{block_type}", "reason": "unsupported_block_type"})
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:{block_type} (unsupported block)")
            continue

        if not raw_p:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "empty_paragraph"})
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (empty paragraph)")
            continue

        visible = strip_tags(raw_p)
        time_match = TIME_RE.match(visible)
        if not time_match:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "no_leading_time"})
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (no leading time)")
            continue

        normalized = normalize_time(time_match.group(1), time_match.group(2))
        if normalized is None:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "no_leading_time"})
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (invalid time)")
            continue

        summary = time_match.group(3).strip()
        if not summary and not config.allow_empty_summary:
            ignored_blocks.append({"type": "wp:paragraph", "reason": "empty_summary"})
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (empty summary)")
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
            print(f"[DEBUG] Accepted entry #{len(entries)}: {normalized} {summary}")

    entries = apply_event_timing_rules(
        entries,
        default_last_event_minutes=config.default_last_event_minutes,
        auto_cross_midnight=config.auto_cross_midnight,
    )
    if verbose:
        print(f"[INFO] Parsed entries: {len(entries)}")
        print(f"[INFO] Ignored blocks: {len(ignored_blocks)}")

    if verbose:
        print(f"[INFO] Parsed entries: {len(parsed.entries)}")
        print(f"[INFO] Ignored blocks: {len(parsed.ignored_blocks)}")
        for warn in parsed.warnings:
            print(f"[WARN] {warn.message}")
    return parsed
