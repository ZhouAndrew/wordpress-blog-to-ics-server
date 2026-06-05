from __future__ import annotations

import re

from .config import AppConfig
from .extractor import strip_tags
from .line_patterns import compile_custom_patterns, parse_log_line
from .models import IgnoredBlock, LogEntry, ParsedPost
from .timeline import apply_timeline
from .wordpress_blocks import iter_blocks


PARAGRAPH_RE = re.compile(r"<p\b[^>]*>.*?</p>", re.DOTALL | re.IGNORECASE)


def parse_post_content(
    post_content: str,
    post_date: str,
    config: AppConfig,
    verbose: bool = False,
) -> ParsedPost:
    custom_patterns = compile_custom_patterns(config)
    entries: list[LogEntry] = []
    ignored_blocks: list[IgnoredBlock] = []

    def _should_append_unmatched() -> bool:
        return getattr(config, "unmatched_line_policy", "ignore") == "append_to_previous"

    def _append_to_previous(raw_html: str, visible: str) -> bool:
        if not entries or not _should_append_unmatched():
            return False
        addition = visible.strip()
        if not addition:
            return False
        previous = entries[-1]
        previous.summary = f"{previous.summary} {addition}".strip()
        previous.raw = f"{previous.raw}\n{raw_html}" if previous.raw else raw_html
        return True

    def _append_parsed_entry(index: int, raw_html: str, visible: str) -> None:
        nonlocal entries, ignored_blocks
        visible = visible.strip()
        if not visible:
            ignored_blocks.append(
                IgnoredBlock(
                    index=index,
                    type="wp:paragraph",
                    reason="empty_paragraph",
                    raw=raw_html,
                )
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (empty paragraph)")
            return

        parsed_line = parse_log_line(visible, config, custom_patterns)
        if parsed_line is None:
            if _append_to_previous(raw_html, visible):
                if verbose:
                    print(f"[DEBUG] Appended unmatched paragraph #{index} to previous entry")
                return
            ignored_blocks.append(
                IgnoredBlock(
                    index=index,
                    type="wp:paragraph",
                    reason="no_leading_time",
                    raw=raw_html,
                )
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (no leading time)")
            return

        summary = parsed_line.summary.strip()
        if not summary and not config.allow_empty_summary:
            ignored_blocks.append(
                IgnoredBlock(
                    index=index,
                    type="wp:paragraph",
                    reason="empty_summary",
                    raw=raw_html,
                )
            )
            if verbose:
                print(f"[DEBUG] Ignored block #{index}: wp:paragraph (empty summary)")
            return

        entries.append(
            LogEntry(
                date=post_date,
                start_time=parsed_line.start_time,
                end_time=parsed_line.end_time,
                summary=summary,
                raw=raw_html,
                status="needs_review",
            )
        )
        if verbose:
            print(f"[DEBUG] Accepted entry #{len(entries)}: {parsed_line.start_time} {summary}")

    if config.log_format == "rendered_html":
        paragraphs = list(PARAGRAPH_RE.finditer(post_content))
        if verbose:
            print(f"[INFO] Extracted rendered HTML paragraphs: {len(paragraphs)}")
            print("[INFO] Scanning paragraphs for timed entries")
        for index, paragraph_match in enumerate(paragraphs, start=1):
            raw_html = paragraph_match.group(0).strip()
            _append_parsed_entry(index, raw_html, strip_tags(raw_html))
    else:
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
                        raw=block.raw_content or block.raw_paragraph_html or "",
                    )
                )
                if verbose:
                    print(f"[DEBUG] Ignored block #{block.index}: wp:{block_type} (unsupported block)")
                continue
            _append_parsed_entry(block.index, block.raw_paragraph_html or "", block.visible_text or "")

    entries, warnings = apply_timeline(entries, config)

    if verbose:
        print(f"[INFO] Parsed entries: {len(entries)}")
        print(f"[INFO] Ignored blocks: {len(ignored_blocks)}")
        for warn in warnings:
            print(f"[WARN] {warn.message}")

    parsed = ParsedPost(
        post_date=post_date,
        entries=entries,
        ignored_blocks=ignored_blocks,
        warnings=warnings,
    )
    parsed.refresh_ics_preview(config.timezone)
    return parsed
