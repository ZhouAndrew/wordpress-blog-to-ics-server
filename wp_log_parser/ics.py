from __future__ import annotations

import hashlib
from datetime import datetime, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo


def escape_ics_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(ch for ch in value if ch == "\n" or ord(ch) >= 0x20)
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;").replace(",", "\\,")
    value = value.replace("\n", "\\n")
    return value


def fold_ics_content_line(line: str, limit: int = 75) -> list[str]:
    encoded = line.encode("utf-8")
    if len(encoded) <= limit:
        return [line]

    chunks: list[bytes] = []
    prefix = b""
    while encoded:
        room = limit - len(prefix)
        split = min(len(encoded), room)
        while split > 0:
            try:
                candidate = encoded[:split].decode("utf-8")
                break
            except UnicodeDecodeError:
                split -= 1
        if split == 0:
            raise ValueError("Unable to fold ICS line without splitting UTF-8 sequence")
        chunks.append(prefix + candidate.encode("utf-8"))
        encoded = encoded[split:]
        prefix = b" "
    return [chunk.decode("utf-8") for chunk in chunks]


def serialize_ics_lines(lines: list[str]) -> str:
    folded: list[str] = []
    for line in lines:
        folded.extend(fold_ics_content_line(line))
    return "\r\n".join(folded) + "\r\n"


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


def to_utc_datetime(value: datetime, timezone: str = "UTC") -> datetime:
    """Return ``value`` as a UTC-aware datetime.

    Naive datetimes are interpreted as local wall-clock times in ``timezone``.
    Aware datetimes already carry an instant, so they are only normalized to UTC.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=ZoneInfo(timezone))
    return value.astimezone(dt_timezone.utc)


def format_ics_utc_datetime(value: datetime, timezone: str = "UTC") -> str:
    return to_utc_datetime(value, timezone).strftime("%Y%m%dT%H%M%SZ")



def generate_single_event_ics(
    *,
    uid: str,
    summary: str,
    start_dt: datetime,
    timezone: str = "UTC",
    end_dt: datetime | None = None,
    sequence: int = 0,
    status: str = "CONFIRMED",
) -> str:
    dtstamp = datetime.now(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"SEQUENCE:{sequence}",
        f"STATUS:{status}",
        f"DTSTART:{format_ics_utc_datetime(start_dt, timezone)}",
        "X-WP-LOG-PARSER-MANAGED:TRUE",
    ]
    if end_dt is not None:
        lines.append(f"DTEND:{format_ics_utc_datetime(end_dt, timezone)}")
    lines.append(f"SUMMARY:{escape_ics_text(summary)}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return serialize_ics_lines(lines)

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
                f"DTSTART:{format_ics_utc_datetime(start_dt, timezone)}",
                "X-WP-LOG-PARSER-MANAGED:TRUE",
            ]
        )
        source_identity = _entry_value(entry, "source_id")
        if source_identity:
            lines.append(f"X-WP-LOG-PARSER-SOURCE:{escape_ics_text(str(source_identity))}")

        if end_dt is not None:
            lines.append(f"DTEND:{format_ics_utc_datetime(end_dt, timezone)}")

        lines.append(f"SUMMARY:{escape_ics_text(str(_entry_value(entry, 'summary', '')))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return serialize_ics_lines(lines)
