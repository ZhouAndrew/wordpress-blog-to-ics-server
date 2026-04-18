from __future__ import annotations

import hashlib
from datetime import UTC, datetime


def escape_ics_text(value: str) -> str:
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;").replace(",", "\\,")
    value = value.replace("\n", "\\n")
    return value


def uid_for_entry(entry: dict) -> str:
    base = f"{entry['date']}|{entry['start_time']}|{entry['summary']}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"wp-log-{digest}"


def build_public_ics_url(ics_base_url: str, filename: str) -> str | None:
    if not ics_base_url:
        return None
    return f"{ics_base_url.rstrip('/')}/{filename.lstrip('/')}"


def generate_ics(entries: list[dict], timezone: str = "UTC") -> str:
    dtstamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for entry in entries:
        start_dt = datetime.strptime(f"{entry['date']} {entry['start_time']}", "%Y-%m-%d %H:%M")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid_for_entry(entry)}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;TZID={timezone}:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            ]
        )

        if entry.get("end_time"):
            end_dt = datetime.strptime(f"{entry['date']} {entry['end_time']}", "%Y-%m-%d %H:%M")
            lines.append(f"DTEND;TZID={timezone}:{end_dt.strftime('%Y%m%dT%H%M%S')}")

        lines.append(f"SUMMARY:{escape_ics_text(entry['summary'])}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
