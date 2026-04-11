import hashlib
import html
import json
import re
from typing import Any

PARAGRAPH_BLOCK_RE = re.compile(
    r"<!--\s*wp:paragraph\s*-->\s*(<p>.*?</p>)\s*<!--\s*/wp:paragraph\s*-->",
    re.DOTALL,
)
BLOCK_RE = re.compile(r"<!--\s*wp:([^\s]+).*?-->", re.DOTALL)
TIME_PREFIX_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?:\s+(.*)|\s*)$", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    return TAG_RE.sub("", text)


def normalize_time(hour: str, minute: str) -> str:
    return f"{int(hour):02d}:{minute}"


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def deterministic_uid(date: str, start_time: str, summary: str, domain: str = "example.com") -> str:
    base = f"{date}|{start_time}|{summary}".encode("utf-8")
    digest = hashlib.sha1(base).hexdigest()[:16]
    return f"{date.replace('-', '')}-{start_time.replace(':', '')}-{digest}@{domain}"


def parse_post_content(post_content: str, post_date: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    ignored_blocks: list[dict[str, str]] = []

    for block_match in BLOCK_RE.finditer(post_content):
        block_type = block_match.group(1)

        if block_type != "paragraph":
            ignored_blocks.append(
                {"type": f"wp:{block_type}", "reason": "not a paragraph or no valid time"}
            )

    for paragraph_match in PARAGRAPH_BLOCK_RE.finditer(post_content):
        raw_paragraph = paragraph_match.group(1)
        visible_text = html.unescape(strip_tags(raw_paragraph)).strip()

        time_match = TIME_PREFIX_RE.match(visible_text)
        if not time_match:
            ignored_blocks.append(
                {"type": "wp:paragraph", "reason": "not a paragraph or no valid time"}
            )
            continue

        hour, minute, summary = time_match.groups()
        start_time = normalize_time(hour, minute)
        entries.append(
            {
                "date": post_date,
                "start_time": start_time,
                "end_time": None,
                "summary": (summary or "").strip(),
                "status": "needs_review",
                "raw": raw_paragraph,
            }
        )

    for idx in range(len(entries) - 1):
        entries[idx]["end_time"] = entries[idx + 1]["start_time"]
        entries[idx]["status"] = "ready"

    ics_preview = build_ics(entries)
    return {"entries": entries, "ignored_blocks": ignored_blocks, "ics_preview": ics_preview}


def build_ics(entries: list[dict[str, Any]]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
    ]

    for entry in entries:
        yyyymmdd = entry["date"].replace("-", "")
        hhmm = entry["start_time"].replace(":", "")
        uid = deterministic_uid(entry["date"], entry["start_time"], entry["summary"])

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART:{yyyymmdd}T{hhmm}00",
            ]
        )

        if entry["end_time"]:
            end_hhmm = entry["end_time"].replace(":", "")
            lines.append(f"DTEND:{yyyymmdd}T{end_hhmm}00")

        lines.append(f"SUMMARY:{escape_ics_text(entry['summary'])}")

        if entry["status"] == "needs_review":
            lines.append("X-STATUS:NEEDS_REVIEW")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


if __name__ == "__main__":
    sample_post_content = """<!-- wp:paragraph -->
<p>07:45 Into the breakfast and bake the pizza</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>07:48 Bake two pizzas for two minutes and 15 seconds</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>08:13 I finished the dinner and have some snacks for sample the beef a small stick of beef</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>8:30 I enabled Thunderbird on laptop</p>
<!-- /wp:paragraph -->

<!-- wp:file {\"id\":10221} -->
<div class=\"wp-block-file\">example</div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>9:56 I found the homework</p>
<!-- /wp:paragraph -->

<!-- wp:image {\"id\":10219} -->
<figure class=\"wp-block-image\">image</figure>
<!-- /wp:image -->

<!-- wp:paragraph -->
<p>10:11</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p></p>
<!-- /wp:paragraph -->"""

    result = parse_post_content(sample_post_content, post_date="2026-04-11")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(result["ics_preview"])
