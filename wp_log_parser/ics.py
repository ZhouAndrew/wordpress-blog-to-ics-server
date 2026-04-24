from __future__ import annotations

import hashlib
from datetime import datetime, timezone as dt_timezone
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


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported datetime value: {type(value)!r}")


def generate_ics(entries: list[Any], timezone: str = "UTC") -> str:
    dtstamp = datetime.now(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for entry in entries:
        start_dt = _coerce_datetime(_entry_value(entry, "start_dt"))
        if start_dt is None:
            raise ValueError("Each entry must include start_dt for ICS serialization.")
        end_dt = _coerce_datetime(_entry_value(entry, "end_dt"))
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

        if end_dt is not None:
            lines.append(f"DTEND;TZID={timezone}:{end_dt.strftime('%Y%m%dT%H%M%S')}")

        lines.append(f"SUMMARY:{escape_ics_text(str(_entry_value(entry, 'summary', '')))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
