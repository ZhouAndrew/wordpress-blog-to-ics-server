from __future__ import annotations

"""
Incremental CalDAV sync engine.

Current deletion strategy issues CalDAV DELETE for removed events.
Some stricter clients/servers may eventually require tombstone/CANCELLED behavior
instead of hard deletes; keep this in mind for a future compatibility pass.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from ..config import AppConfig
from ..fetcher import fetch_post, normalize_post_date
from ..parser import parse_post_content
from ..wordpress import list_posts_rest, list_posts_wpcli


@dataclass
class PostSyncState:
    modified_gmt: str
    content_hash: str
    event_uids: list[str]


@dataclass
class EventSyncState:
    post_id: int
    hash: str


@dataclass
class SyncIndex:
    posts: dict[str, PostSyncState] = field(default_factory=dict)
    events: dict[str, EventSyncState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "SyncIndex":
        idx_path = Path(path)
        if not idx_path.exists():
            return cls()

        payload = json.loads(idx_path.read_text(encoding="utf-8"))
        posts = {
            str(post_id): PostSyncState(
                modified_gmt=str(data.get("modified_gmt", "")),
                content_hash=str(data.get("content_hash", "")),
                event_uids=[str(uid) for uid in data.get("event_uids", [])],
            )
            for post_id, data in payload.get("posts", {}).items()
        }
        events = {
            str(uid): EventSyncState(post_id=int(data["post_id"]), hash=str(data["hash"]))
            for uid, data in payload.get("events", {}).items()
        }
        return cls(posts=posts, events=events)

    def save(self, path: str | Path) -> None:
        idx_path = Path(path)
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "posts": {
                post_id: {
                    "modified_gmt": state.modified_gmt,
                    "content_hash": state.content_hash,
                    "event_uids": state.event_uids,
                }
                for post_id, state in self.posts.items()
            },
            "events": {
                uid: {"post_id": state.post_id, "hash": state.hash}
                for uid, state in self.events.items()
            },
        }
        idx_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class CalDAVTransport:
    def put(self, resource_path: str, ics_payload: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, resource_path: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class RequestsCalDAVTransport(CalDAVTransport):
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

    def _resource_url(self, resource_path: str) -> str:
        return f"{self.base_url}/{resource_path.lstrip('/')}"

    def put(self, resource_path: str, ics_payload: str) -> None:
        import requests

        response = requests.put(
            self._resource_url(resource_path),
            data=ics_payload.encode("utf-8"),
            auth=(self.username, self.password),
            verify=self.verify_ssl,
            headers={"Content-Type": "text/calendar; charset=utf-8"},
            timeout=20,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(f"CalDAV PUT failed for {resource_path}: HTTP {response.status_code}")

    def delete(self, resource_path: str) -> None:
        import requests

        response = requests.delete(
            self._resource_url(resource_path),
            auth=(self.username, self.password),
            verify=self.verify_ssl,
            timeout=20,
        )
        if response.status_code not in {200, 204, 404}:
            raise RuntimeError(f"CalDAV DELETE failed for {resource_path}: HTTP {response.status_code}")


class DryRunCalDAVTransport(CalDAVTransport):
    def __init__(self) -> None:
        self.puts: list[str] = []
        self.deletes: list[str] = []

    def put(self, resource_path: str, ics_payload: str) -> None:
        _ = ics_payload
        self.puts.append(resource_path)

    def delete(self, resource_path: str) -> None:
        self.deletes.append(resource_path)


@dataclass
class SyncOperationSummary:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    changed_posts: int = 0


@dataclass
class _RenderedEvent:
    uid: str
    post_id: int
    hash: str
    resource_path: str
    ics_payload: str


def _canonical_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _event_hash(summary: str, start_utc: datetime, end_utc: datetime | None) -> str:
    material = "|".join(
        [
            summary,
            start_utc.isoformat(),
            end_utc.isoformat() if end_utc else "",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _vevent_resource(uid: str) -> str:
    return f"{quote(uid, safe='@-_.')}.ics"


def _to_utc(naive_dt: datetime, tz_name: str) -> datetime:
    local_tz = ZoneInfo(tz_name)
    return naive_dt.replace(tzinfo=local_tz).astimezone(timezone.utc)


def _single_event_ics(uid: str, summary: str, start_utc: datetime, end_utc: datetime | None) -> str:
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wordpress-blog-to-ics-server//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}",
        "X-WP-LOG-PARSER-MANAGED:TRUE",
    ]
    if end_utc is not None:
        lines.append(f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}")
    escaped = summary.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    lines.append(f"SUMMARY:{escaped}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\r\n".join(lines) + "\r\n"


def _list_post_metadata(config: AppConfig, per_page: int = 100) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    page = 1
    seen_ids: set[int] = set()

    while True:
        if config.wordpress_mode == "wpcli":
            page_rows = list_posts_wpcli(
                config.wp_path,
                config.wp_cli_path,
                per_page=per_page,
                limit=None,
                page=page,
            )
        else:
            page_rows = list_posts_rest(
                config.base_url,
                config.username,
                config.app_password,
                config.verify_ssl,
                per_page=per_page,
                limit=None,
                page=page,
            )

        if not page_rows:
            break

        new_rows = 0
        for row in page_rows:
            post_id = int(row["id"])
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            if not row.get("modified_gmt"):
                row["modified_gmt"] = str(row.get("date", ""))
            posts.append(row)
            new_rows += 1

        # stop on short page or no new IDs (safety against buggy paging responses)
        if len(page_rows) < per_page or new_rows == 0:
            break
        page += 1

    return posts


def _uid_for_entry(post_id: int, start_utc: datetime, same_start_ordinal: int, uid_domain: str) -> str:
    ts = start_utc.strftime("%Y%m%dT%H%M%SZ")
    return f"wp-{post_id}-{ts}-{same_start_ordinal}@{uid_domain}"


def _render_post_events(post_id: int, post_date: str, post_content: str, config: AppConfig, uid_domain: str) -> list[_RenderedEvent]:
    parsed = parse_post_content(post_content, normalize_post_date(post_date), config)
    parsed.post_id = post_id
    parsed.source_id = f"wp:{post_id}"

    events: list[_RenderedEvent] = []
    same_start_counts: defaultdict[str, int] = defaultdict(int)

    for entry in parsed.entries:
        if entry.start_dt is None:
            continue

        start_utc = _to_utc(entry.start_dt, config.timezone)
        end_utc = _to_utc(entry.end_dt, config.timezone) if entry.end_dt else None

        start_key = start_utc.strftime("%Y%m%dT%H%M%SZ")
        same_start_counts[start_key] += 1
        ordinal = same_start_counts[start_key]

        uid = _uid_for_entry(post_id, start_utc, ordinal, uid_domain)
        digest = _event_hash(entry.summary, start_utc, end_utc)
        events.append(
            _RenderedEvent(
                uid=uid,
                post_id=post_id,
                hash=digest,
                resource_path=_vevent_resource(uid),
                ics_payload=_single_event_ics(uid, entry.summary, start_utc, end_utc),
            )
        )
    return events


def sync_caldav_once(
    config: AppConfig,
    *,
    index_path: str,
    uid_domain: str,
    transport: CalDAVTransport,
    dry_run: bool = False,
) -> dict[str, Any]:
    index = SyncIndex.load(index_path)
    summary = SyncOperationSummary()

    posts = _list_post_metadata(config)
    post_map = {int(item["id"]): item for item in posts}

    for post_id, meta in post_map.items():
        post_id_key = str(post_id)
        prev = index.posts.get(post_id_key)
        modified_gmt = str(meta.get("modified_gmt", ""))

        if prev is not None and prev.modified_gmt == modified_gmt:
            continue

        post = fetch_post(config, post_id)
        content_hash = _canonical_content_hash(post.post_content)
        if prev is not None and prev.modified_gmt != modified_gmt and prev.content_hash == content_hash:
            if not dry_run:
                index.posts[post_id_key] = PostSyncState(
                    modified_gmt=modified_gmt,
                    content_hash=content_hash,
                    event_uids=prev.event_uids,
                )
            continue

        summary.changed_posts += 1
        rendered_events = _render_post_events(post_id, post.post_date, post.post_content, config, uid_domain)
        new_by_uid = {event.uid: event for event in rendered_events}
        old_uids = set(prev.event_uids if prev else [])
        new_uids = set(new_by_uid)

        for uid in sorted(new_uids - old_uids):
            event = new_by_uid[uid]
            transport.put(event.resource_path, event.ics_payload)
            if not dry_run:
                index.events[uid] = EventSyncState(post_id=post_id, hash=event.hash)
            summary.created += 1

        for uid in sorted(new_uids & old_uids):
            event = new_by_uid[uid]
            old_event = index.events.get(uid)
            if old_event is None or old_event.hash != event.hash:
                transport.put(event.resource_path, event.ics_payload)
                summary.updated += 1
            if not dry_run:
                index.events[uid] = EventSyncState(post_id=post_id, hash=event.hash)

        for uid in sorted(old_uids - new_uids):
            transport.delete(_vevent_resource(uid))
            if not dry_run:
                index.events.pop(uid, None)
            summary.deleted += 1

        if not dry_run:
            index.posts[post_id_key] = PostSyncState(
                modified_gmt=modified_gmt,
                content_hash=content_hash,
                event_uids=[event.uid for event in rendered_events],
            )

    # Remove state for posts no longer listed in source.
    stale_post_ids = set(index.posts) - {str(pid) for pid in post_map}
    for stale_post_id in sorted(stale_post_ids):
        stale_state = index.posts[stale_post_id]
        for uid in stale_state.event_uids:
            transport.delete(_vevent_resource(uid))
            if not dry_run:
                index.events.pop(uid, None)
            summary.deleted += 1
        if not dry_run:
            index.posts.pop(stale_post_id, None)

    if not dry_run:
        index.save(index_path)

    return {
        "created": summary.created,
        "updated": summary.updated,
        "deleted": summary.deleted,
        "changed_posts": summary.changed_posts,
        "dry_run": dry_run,
        "index_path": str(index_path),
    }


def run_caldav_sync(config: AppConfig, dry_run: bool = False) -> dict[str, Any]:
    transport: CalDAVTransport
    if dry_run:
        transport = DryRunCalDAVTransport()
    else:
        transport = RequestsCalDAVTransport(
            config.caldav_url,
            config.caldav_username,
            config.caldav_password,
            verify_ssl=config.verify_ssl,
        )

    return sync_caldav_once(
        config,
        index_path=config.caldav_index_path,
        uid_domain=config.caldav_uid_domain,
        transport=transport,
        dry_run=dry_run,
    )
