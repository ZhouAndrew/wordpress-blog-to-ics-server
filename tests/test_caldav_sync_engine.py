from __future__ import annotations

from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import PostData
from wp_log_parser.sync.caldav_sync import (
    CalDAVTransport,
    SyncIndex,
    _list_post_metadata,
    run_caldav_sync,
    sync_caldav_once,
)


class FakeTransport(CalDAVTransport):
    def __init__(self) -> None:
        self.puts: list[str] = []
        self.put_payloads: dict[str, str] = {}
        self.deletes: list[str] = []

    def put(self, resource_path: str, ics_payload: str) -> None:
        self.puts.append(resource_path)
        self.put_payloads[resource_path] = ics_payload

    def delete(self, resource_path: str) -> None:
        self.deletes.append(resource_path)


def _post_content(*lines: str) -> str:
    blocks = []
    for line in lines:
        blocks.append(f"<!-- wp:paragraph --><p>{line}</p><!-- /wp:paragraph -->")
    return "\n".join(blocks)


def test_sync_twice_without_changes_is_noop(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0)
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": "2026-04-01 10:00:00"}]

    def fetch(_config: AppConfig, post_id: int):
        assert post_id == 10
        return PostData(
            post_id=10,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=_post_content("07:45 Breakfast", "08:30 Work"),
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    first = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    assert first["created"] == 2
    assert first["updated"] == 0
    assert first["deleted"] == 0
    assert first["cancelled"] == 0
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["deleted"] == 0
    assert second["cancelled"] == 0


def test_modified_post_updates_and_deletes_removed_entries(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0)
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    first = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast Updated")
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    assert first["created"] == 2
    assert second["updated"] == 1
    assert second["deleted"] == 1
    assert second["cancelled"] == 0
    assert all(item.endswith(".ics") for item in transport.puts)
    assert "wp-10-20260401T083000Z-1@example.com.ics" in transport.deletes


def test_inserted_middle_entry_does_not_rewrite_unrelated_later_uids(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0)
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "09:00 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    first = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    index_first = SyncIndex.load(idx_path)
    original_second_uid = index_first.posts["10"].event_uids[1]

    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast", "08:00 New entry", "09:00 Work")
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    index_second = SyncIndex.load(idx_path)

    assert first["created"] == 2
    assert second["created"] == 1
    assert second["updated"] == 1
    assert second["deleted"] == 0
    assert second["cancelled"] == 0
    assert original_second_uid in index_second.posts["10"].event_uids


def test_dry_run_reports_changes_without_writing_index(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0)
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": "2026-04-01 10:00:00"}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=_post_content("07:45 Breakfast"),
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport, dry_run=True)

    assert result["dry_run"] is True
    assert result["created"] == 1
    assert idx_path.exists() is False
    assert transport.puts == []
    assert transport.deletes == []


def test_metadata_listing_uses_pagination(monkeypatch) -> None:
    config = AppConfig(wordpress_mode="wpcli")

    def list_wpcli(_wp_path, _wp_cli_path, per_page, limit, page):
        assert per_page == 100
        assert limit is None
        if page == 1:
            return [{"id": 1, "date": "2026-01-01 00:00:00", "modified_gmt": "2026-01-01 00:00:00"}]
        return []

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.list_posts_wpcli", list_wpcli)

    rows = _list_post_metadata(config)
    assert len(rows) == 1
    assert rows[0]["id"] == 1


def test_changed_start_time_results_in_delete_and_create(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0)
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    first = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:50 Breakfast")
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    assert first["created"] == 1
    assert second["created"] == 1
    assert second["deleted"] == 1
    assert second["cancelled"] == 0
    assert second["updated"] == 0


def test_run_caldav_sync_dry_run_never_uses_requests_transport(monkeypatch) -> None:
    config = AppConfig(
        caldav_url="https://caldav.example.com/user/calendar",
        caldav_username="alice",
        caldav_password="secret",
    )

    monkeypatch.setattr(
        "wp_log_parser.sync.caldav_sync.RequestsCalDAVTransport",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Requests transport must not be constructed")),
    )
    monkeypatch.setattr(
        "wp_log_parser.sync.caldav_sync.sync_caldav_once",
        lambda *_args, **kwargs: {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "cancelled": 0,
            "skipped": 0,
            "changed_posts": 0,
            "dry_run": True,
            "index_path": "sync-index.json",
        },
    )

    result = run_caldav_sync(config, dry_run=True)
    assert result["dry_run"] is True


def test_cancel_mode_puts_cancelled_instead_of_delete(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    first = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast Updated")
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    assert first["created"] == 2
    assert second["deleted"] == 0
    assert second["cancelled"] == 1
    assert transport.deletes == []
    assert "wp-10-20260401T083000Z-1@example.com.ics" in transport.puts
    cancelled_payload = transport.put_payloads["wp-10-20260401T083000Z-1@example.com.ics"]
    assert "STATUS:CANCELLED" in cancelled_payload
    index = SyncIndex.load(idx_path)
    cancelled = index.events["wp-10-20260401T083000Z-1@example.com"]
    assert cancelled.status == "cancelled"
    assert cancelled.resource_path == "wp-10-20260401T083000Z-1@example.com.ics"
    assert "wp-10-20260401T083000Z-1@example.com" in index.posts["10"].cancelled_uids


def test_cancelled_uid_can_be_restored_with_same_resource_and_incremented_sequence(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast")
    remove_result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    cancel_payload = transport.put_payloads["wp-10-20260401T083000Z-1@example.com.ics"]
    assert remove_result["cancelled"] == 1
    assert "STATUS:CANCELLED" in cancel_payload
    assert "SEQUENCE:1" in cancel_payload

    state["modified"] = "2026-04-03 10:00:00"
    state["content"] = _post_content("07:45 Breakfast", "08:30 Work")
    restore_result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    restored_payload = transport.put_payloads["wp-10-20260401T083000Z-1@example.com.ics"]
    assert restore_result["updated"] >= 1
    assert "STATUS:CONFIRMED" in restored_payload
    assert "SEQUENCE:2" in restored_payload

    index = SyncIndex.load(idx_path)
    restored = index.events["wp-10-20260401T083000Z-1@example.com"]
    assert restored.status == "confirmed"
    assert restored.resource_path == "wp-10-20260401T083000Z-1@example.com.ics"
    assert restored.sequence == 2


def test_cancelled_tombstone_persists_across_unrelated_post_change(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast")
    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    state["modified"] = "2026-04-03 10:00:00"
    state["content"] = _post_content("07:45 Breakfast Updated")
    third = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    assert third["cancelled"] == 0
    index = SyncIndex.load(idx_path)
    assert "wp-10-20260401T083000Z-1@example.com" in index.posts["10"].cancelled_uids
    tombstone = index.events["wp-10-20260401T083000Z-1@example.com"]
    assert tombstone.status == "cancelled"


def test_cancel_mode_missing_index_fields_is_counted_as_skipped(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-02 10:00:00", "content": _post_content("07:45 Breakfast")}

    idx_path.write_text(
        """
{
  "version": 2,
  "updated_at": "2026-04-01T00:00:00+00:00",
  "posts": {
    "10": {
      "modified_gmt": "2026-04-01 10:00:00",
      "content_hash": "abc",
      "event_uids": ["wp-10-20260401T083000Z-1@example.com"],
      "cancelled_uids": []
    }
  },
  "events": {
    "wp-10-20260401T083000Z-1@example.com": {
      "uid": "wp-10-20260401T083000Z-1@example.com",
      "post_id": 10,
      "resource_path": "wp-10-20260401T083000Z-1@example.com.ics",
      "start_utc": "",
      "end_utc": null,
      "summary": "Work",
      "hash": "abc",
      "sequence": 0,
      "status": "confirmed"
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    assert result["cancelled"] == 0
    assert result["skipped"] == 1
    assert transport.puts == ["wp-10-20260401T074500Z-1@example.com.ics"]


def test_debug_events_capture_create_cancel_restore_and_skip(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"
    debug_events: list[dict[str, object]] = []
    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, _post_id: int):
        return PostData(
            post_id=10,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport, debug_events=debug_events)
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast")
    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport, debug_events=debug_events)
    state["modified"] = "2026-04-03 10:00:00"
    state["content"] = _post_content("07:45 Breakfast", "08:30 Work")
    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport, debug_events=debug_events)

    # Skip case from malformed index tombstone.
    idx_path.write_text(
        """
{
  "version": 2,
  "updated_at": "2026-04-01T00:00:00+00:00",
  "posts": {"10": {"modified_gmt": "2026-04-03 10:00:00", "content_hash": "x", "event_uids": ["wp-10-20260401T083000Z-1@example.com"], "cancelled_uids": []}},
  "events": {"wp-10-20260401T083000Z-1@example.com": {"uid": "wp-10-20260401T083000Z-1@example.com", "post_id": 10, "resource_path": "wp-10-20260401T083000Z-1@example.com.ics", "start_utc": "", "end_utc": null, "summary": "Work", "hash": "x", "sequence": 1, "status": "confirmed"}}
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    state["modified"] = "2026-04-04 10:00:00"
    state["content"] = _post_content("07:45 Breakfast")
    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport, debug_events=debug_events)

    operations = {item["operation"] for item in debug_events}
    assert "create" in operations
    assert "cancel" in operations
    assert "restore" in operations
    assert "skip" in operations


def test_changed_event_increments_sequence_and_active_event_has_sequence(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0)
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    first_payload = transport.put_payloads["wp-10-20260401T074500Z-1@example.com.ics"]
    assert "SEQUENCE:0" in first_payload
    assert "STATUS:CONFIRMED" in first_payload

    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast Updated")
    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    second_payload = transport.put_payloads["wp-10-20260401T074500Z-1@example.com.ics"]
    assert "SEQUENCE:1" in second_payload
    assert "STATUS:CONFIRMED" in second_payload

    index = SyncIndex.load(idx_path)
    assert index.events["wp-10-20260401T074500Z-1@example.com"].sequence == 1


def test_cancel_mode_is_idempotent_on_second_run(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, post_id: int):
        return PostData(
            post_id=post_id,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast Updated")
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    third = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)

    assert second["cancelled"] == 1
    assert third["cancelled"] == 0
    assert third["updated"] == 0
    assert third["deleted"] == 0


def test_cancel_mode_whole_post_removal_is_idempotent(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    transport = FakeTransport()
    idx_path = tmp_path / "sync-index.json"

    state = {"present": True}

    def list_meta(_config: AppConfig):
        if state["present"]:
            return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": "2026-04-01 10:00:00"}]
        return []

    def fetch(_config: AppConfig, post_id: int):
        assert post_id == 10
        return PostData(
            post_id=10,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=_post_content("07:45 Breakfast", "08:30 Work"),
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    first = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    assert first["created"] == 2

    state["present"] = False
    second = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    assert second["cancelled"] == 2
    assert second["deleted"] == 0
    assert transport.deletes == []

    index_second = SyncIndex.load(idx_path)
    assert "10" not in index_second.posts
    assert index_second.events["wp-10-20260401T074500Z-1@example.com"].status == "cancelled"
    assert index_second.events["wp-10-20260401T083000Z-1@example.com"].status == "cancelled"

    third = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=transport)
    assert third["cancelled"] == 0
    assert third["updated"] == 0
    assert third["deleted"] == 0
    assert third["skipped"] == 0
    assert third["created"] == 0


def test_cancel_mode_removed_event_dry_run_does_not_write_transport_or_index(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    idx_path = tmp_path / "sync-index.json"
    setup_transport = FakeTransport()
    dry_transport = FakeTransport()

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, _post_id: int):
        return PostData(
            post_id=10,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=setup_transport)
    before = idx_path.read_text(encoding="utf-8")
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast")

    result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=dry_transport, dry_run=True)
    assert result["cancelled"] == 1
    assert dry_transport.puts == []
    assert dry_transport.deletes == []
    assert idx_path.read_text(encoding="utf-8") == before


def test_cancel_mode_restore_dry_run_does_not_write_transport_or_index(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    idx_path = tmp_path / "sync-index.json"
    setup_transport = FakeTransport()
    dry_transport = FakeTransport()

    state = {"modified": "2026-04-01 10:00:00", "content": _post_content("07:45 Breakfast", "08:30 Work")}

    def list_meta(_config: AppConfig):
        return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": state["modified"]}]

    def fetch(_config: AppConfig, _post_id: int):
        return PostData(
            post_id=10,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=state["content"],
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=setup_transport)
    state["modified"] = "2026-04-02 10:00:00"
    state["content"] = _post_content("07:45 Breakfast")
    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=setup_transport)

    before = idx_path.read_text(encoding="utf-8")
    state["modified"] = "2026-04-03 10:00:00"
    state["content"] = _post_content("07:45 Breakfast", "08:30 Work")
    result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=dry_transport, dry_run=True)
    assert result["updated"] >= 1
    assert dry_transport.puts == []
    assert dry_transport.deletes == []
    assert idx_path.read_text(encoding="utf-8") == before


def test_cancel_mode_stale_post_removal_dry_run_does_not_write_transport_or_index(tmp_path, monkeypatch) -> None:
    config = AppConfig(timezone="UTC", default_last_event_minutes=0, caldav_deletion_mode="cancel")
    idx_path = tmp_path / "sync-index.json"
    setup_transport = FakeTransport()
    dry_transport = FakeTransport()
    state = {"present": True}

    def list_meta(_config: AppConfig):
        if state["present"]:
            return [{"id": 10, "date": "2026-04-01 00:00:00", "modified_gmt": "2026-04-01 10:00:00"}]
        return []

    def fetch(_config: AppConfig, _post_id: int):
        return PostData(
            post_id=10,
            title="day",
            post_date="2026-04-01 00:00:00",
            post_content=_post_content("07:45 Breakfast", "08:30 Work"),
            status="publish",
        )

    monkeypatch.setattr("wp_log_parser.sync.caldav_sync._list_post_metadata", list_meta)
    monkeypatch.setattr("wp_log_parser.sync.caldav_sync.fetch_post", fetch)

    sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=setup_transport)
    before = idx_path.read_text(encoding="utf-8")

    state["present"] = False
    result = sync_caldav_once(config, index_path=idx_path, uid_domain="example.com", transport=dry_transport, dry_run=True)
    assert result["cancelled"] == 2
    assert result["deleted"] == 0
    assert dry_transport.puts == []
    assert dry_transport.deletes == []
    assert idx_path.read_text(encoding="utf-8") == before


def test_sync_index_load_supports_v1_payload_and_upgrades_on_save(tmp_path) -> None:
    idx_path = tmp_path / "sync-index.json"
    idx_path.write_text(
        """
{
  "version": 1,
  "updated_at": "2026-04-01T00:00:00+00:00",
  "posts": {
    "10": {
      "modified_gmt": "2026-04-01 10:00:00",
      "content_hash": "abc",
      "event_uids": ["legacy-uid@example.com"]
    }
  },
  "events": {
    "legacy-uid@example.com": {
      "post_id": 10,
      "hash": "legacy-hash"
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    index = SyncIndex.load(idx_path)
    event = index.events["legacy-uid@example.com"]
    assert event.uid == "legacy-uid@example.com"
    assert event.status == "confirmed"
    assert event.sequence == 0
    assert event.resource_path == "legacy-uid@example.com.ics"
    assert event.start_utc == ""
    assert event.end_utc is None
    assert event.summary == ""
    assert index.posts["10"].cancelled_uids == []

    index.save(idx_path)
    payload = idx_path.read_text(encoding="utf-8")
    assert '"version": 2' in payload
