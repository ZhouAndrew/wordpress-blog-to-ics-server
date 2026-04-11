import hashlib
import html
import json
import re
from datetime import datetime
from typing import List, Optional, Tuple

BLOCK_RE = re.compile(
    r"<!--\s+wp:([a-zA-Z0-9_/:-]+)(?:\s+\{.*?\})?\s+-->(.*?)<!--\s+/wp:\1\s+-->",
    re.DOTALL,
)
PARAGRAPH_RE = re.compile(r"<p\b[^>]*>.*?</p>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
TIME_RE = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\b(.*)$", re.DOTALL)


def _strip_tags(text: str) -> str:
    no_tags = TAG_RE.sub("", text)
    return html.unescape(no_tags).strip()


def _normalize_time(hour: str, minute: str) -> Optional[str]:
    h = int(hour)
    if h < 0 or h > 23:
        return None
    return f"{h:02d}:{minute}"


def parse_post_content(post_content: str, post_date: str) -> dict:
    entries: List[dict] = []
    ignored_blocks: List[dict] = []

    blocks: List[Tuple[str, str]] = BLOCK_RE.findall(post_content)
    for block_type, block_body in blocks:
        p_match = PARAGRAPH_RE.search(block_body)
        if block_type != "paragraph" or not p_match:
            ignored_blocks.append(
                {
                    "type": f"wp:{block_type}",
                    "reason": "not a paragraph or no valid time",
                }
            )
            continue

        raw_p = p_match.group(0).strip()
        visible = _strip_tags(raw_p)
        time_match = TIME_RE.match(visible)
        if not time_match:
            ignored_blocks.append(
                {
                    "type": "wp:paragraph",
                    "reason": "not a paragraph or no valid time",
                }
            )
            continue

        normalized = _normalize_time(time_match.group(1), time_match.group(2))
        if normalized is None:
            ignored_blocks.append(
                {
                    "type": "wp:paragraph",
                    "reason": "not a paragraph or no valid time",
                }
            )
            continue

        summary = time_match.group(3).strip()
        entries.append(
            {
                "date": post_date,
                "start_time": normalized,
                "end_time": None,
                "summary": summary,
                "status": "needs_review",
                "raw": raw_p,
            }
        )

    for i in range(len(entries) - 1):
        entries[i]["end_time"] = entries[i + 1]["start_time"]
        entries[i]["status"] = "ready"

    ics_preview = generate_ics(entries)
    return {"entries": entries, "ignored_blocks": ignored_blocks, "ics_preview": ics_preview}


def _escape_ics_text(value: str) -> str:
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;").replace(",", "\\,")
    value = value.replace("\n", "\\n")
    return value


def _uid_for_entry(entry: dict) -> str:
    base = f"{entry['date']}|{entry['start_time']}|{entry['summary']}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"wp-log-{digest}"


def generate_ics(entries: List[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for entry in entries:
        start_dt = datetime.strptime(f"{entry['date']} {entry['start_time']}", "%Y-%m-%d %H:%M")
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{_uid_for_entry(entry)}")
        lines.append(f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}")

        if entry.get("end_time"):
            end_dt = datetime.strptime(f"{entry['date']} {entry['end_time']}", "%Y-%m-%d %H:%M")
            lines.append(f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}")

        lines.append(f"SUMMARY:{_escape_ics_text(entry['summary'])}")
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

<!-- wp:file {\"id\":10221,\"href\":\"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html\"} -->
<div class=\"wp-block-file\"><a href=\"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-截图问题排查指南.html\">ChatGPT-截图问题排查指南</a></div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>9:56 I found the homework</p>
<!-- /wp:paragraph -->

<!-- wp:image {\"id\":10219} -->
<figure class=\"wp-block-image\"><img src=\"https://andrew.local/wp-content/uploads/2026/04/8b45.jpg\" alt=\"\"/></figure>
<!-- /wp:image -->

<!-- wp:file {\"id\":10224,\"href\":\"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html\"} -->
<div class=\"wp-block-file\"><a href=\"https://andrew.local/wp-content/uploads/2026/04/ChatGPT-Transfer_Thunderbird_Data.html\">ChatGPT-Transfer_Thunderbird_Data</a></div>
<!-- /wp:file -->

<!-- wp:paragraph -->
<p>10:11</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p></p>
<!-- /wp:paragraph -->"""

    parsed = parse_post_content(sample_post_content, post_date="2026-04-11")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
