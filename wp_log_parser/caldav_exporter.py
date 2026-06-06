from __future__ import annotations

"""CalDAV-oriented structured event rendering.

This module is the exporter boundary for CalDAV sync: it receives parsed log
entries and renders deterministic event DTOs plus VEVENT payloads. It does not
perform any CalDAV transport operations.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from .config import AppConfig
from .ics import generate_single_event_ics, to_utc_datetime
from .models import ParsedPost


@dataclass(frozen=True)
class CalDAVRenderedEvent:
    uid: str
    post_id: int
    summary: str
    start_utc: datetime
    end_utc: datetime | None
    hash: str
    resource_path: str
    ics_payload: str


def canonical_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def event_hash(summary: str, start_utc: datetime, end_utc: datetime | None) -> str:
    material = "|".join(
        [
            summary,
            start_utc.isoformat(),
            end_utc.isoformat() if end_utc else "",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def vevent_resource(uid: str) -> str:
    return f"{quote(uid, safe='@-_.')}.ics"


def uid_for_entry(
    post_id: int, start_utc: datetime, same_start_ordinal: int, uid_domain: str
) -> str:
    ts = start_utc.strftime("%Y%m%dT%H%M%SZ")
    return f"wp-{post_id}-{ts}-{same_start_ordinal}@{uid_domain}"


def render_confirmed_event_payload(
    *,
    uid: str,
    summary: str,
    start_utc: datetime,
    end_utc: datetime | None,
    sequence: int = 0,
) -> str:
    return generate_single_event_ics(
        uid=uid,
        summary=summary,
        start_dt=start_utc,
        end_dt=end_utc,
        sequence=sequence,
        status="CONFIRMED",
    )


def render_cancelled_event_payload(
    *,
    uid: str,
    summary: str,
    start_utc: datetime,
    end_utc: datetime | None,
    sequence: int,
) -> str:
    return generate_single_event_ics(
        uid=uid,
        summary=summary,
        start_dt=start_utc,
        end_dt=end_utc,
        sequence=sequence,
        status="CANCELLED",
    )


def render_parsed_post_events(
    parsed: ParsedPost,
    *,
    post_id: int,
    timezone: str,
    uid_domain: str,
) -> list[CalDAVRenderedEvent]:
    events: list[CalDAVRenderedEvent] = []
    same_start_counts: defaultdict[str, int] = defaultdict(int)

    for entry in parsed.entries:
        if entry.start_dt is None:
            continue

        start_utc = to_utc_datetime(entry.start_dt, timezone)
        end_utc = to_utc_datetime(entry.end_dt, timezone) if entry.end_dt else None

        start_key = start_utc.strftime("%Y%m%dT%H%M%SZ")
        same_start_counts[start_key] += 1
        ordinal = same_start_counts[start_key]

        uid = uid_for_entry(post_id, start_utc, ordinal, uid_domain)
        digest = event_hash(entry.summary, start_utc, end_utc)
        events.append(
            CalDAVRenderedEvent(
                uid=uid,
                post_id=post_id,
                summary=entry.summary,
                start_utc=start_utc,
                end_utc=end_utc,
                hash=digest,
                resource_path=vevent_resource(uid),
                ics_payload=render_confirmed_event_payload(
                    uid=uid,
                    summary=entry.summary,
                    start_utc=start_utc,
                    end_utc=end_utc,
                    sequence=0,
                ),
            )
        )
    return events
