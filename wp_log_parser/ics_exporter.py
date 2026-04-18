from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from .fetcher import PostData
from .ics import generate_ics


def safe_slug(title: str, limit: int = 60) -> str:
    slug = re.sub(r"[^\w\-.]+", "_", title.strip(), flags=re.UNICODE).strip("_")
    return slug[:limit] or "untitled"


def build_output_filename(post: PostData) -> str:
    date_part = post.post_date.split(" ")[0]
    return f"{date_part}_post_{post.post_id}_{safe_slug(post.title)}.ics"


def write_post_ics(post: PostData, entries: list[dict], output_dir: str, timezone: str) -> Path:
    filename = build_output_filename(post)
    path = Path(output_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_ics(entries, timezone=timezone), encoding="utf-8", newline="")
    return path


def write_publish_index(
    output_dir: str,
    items: list[dict],
    days: int,
) -> Path:
    path = Path(output_dir) / "index.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "recent_days": days,
                "published_count": len(items),
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def write_ignored_blocks(output_dir: str, ics_filename: str, ignored_blocks: list[dict]) -> Path:
    path = Path(output_dir) / ics_filename.replace(".ics", ".ignored.json")
    path.write_text(json.dumps(ignored_blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_publish_index_html(output_dir: str, items: list[dict]) -> Path:
    path = Path(output_dir) / "index.html"
    generated_at = datetime.now(UTC).isoformat()
    lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>ICS Publish Index</title></head><body>",
        "<h1>ICS Publish Index</h1>",
        f"<p>Generated at: {escape(generated_at)}</p>",
        "<ul>",
    ]
    for item in items:
        lines.append(
            "<li>"
            f"<a href='{escape(str(item['ics_file']))}'>{escape(str(item['title']))}</a> "
            f"(ID: {item['post_id']}, date: {escape(str(item['post_date']))}, "
            f"entries: {item['entry_count']}, ignored: {item['ignored_block_count']})"
            "</li>"
        )
    lines.extend(["</ul>", "</body></html>"])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
