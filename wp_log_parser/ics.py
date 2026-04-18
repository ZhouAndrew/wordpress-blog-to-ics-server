from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from typing import Any



def escape_ics_text(value: str) -> str:
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;").replace(",", "\\,")
    value = value.replace("\n", "\\n")
    return value


def _entry_value(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def uid_for_entry(entry: Any) -> str:
    source_identity = _entry_value(entry, "source_id") or _entry_value(entry, "post_id") or "wp:unknown"
    base = f"{source_identity}|{_entry_value(entry, 'date')}|{_entry_value(entry, 'start_time')}|{_entry_value(entry, 'summary')}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"wp-log-{digest}@wordpress-blog-to-ics"


def build_public_ics_url(ics_base_url: str, filename: str) -> str | None:
    if not ics_base_url:
        return None
    return f"{ics_base_url.rstrip('/')}/{filename.lstrip('/')}"


def generate_ics(entries: list[dict], timezone: str = "UTC") -> str:
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for entry in entries:
        start_dt = datetime.strptime(f"{_entry_value(entry, 'date')} {_entry_value(entry, 'start_time')}", "%Y-%m-%d %H:%M")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid_for_entry(entry)}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;TZID={timezone}:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                "X-WP-LOG-PARSER-MANAGED:TRUE",
            ]
        )
        source_identity = _entry_value(entry, "source_id")
        if source_identity:
            lines.append(f"X-WP-LOG-PARSER-SOURCE:{escape_ics_text(str(source_identity))}")

        if _entry_value(entry, "end_time"):
            end_dt = datetime.strptime(
                f"{_entry_value(entry, 'date')} {_entry_value(entry, 'end_time')}", "%Y-%m-%d %H:%M"
            )
            lines.append(f"DTEND;TZID={timezone}:{end_dt.strftime('%Y%m%dT%H%M%S')}")

        lines.append(f"SUMMARY:{escape_ics_text(str(_entry_value(entry, 'summary', '')))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
