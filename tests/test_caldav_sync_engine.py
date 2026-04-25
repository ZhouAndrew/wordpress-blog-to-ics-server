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
        self.deletes: list[str] = []

    def put(self, resource_path: str, ics_payload: str) -> None:
        self.puts.append(resource_path)

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
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["deleted"] == 0


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
        lambda *_args, **kwargs: {"created": 0, "updated": 0, "deleted": 0, "changed_posts": 0, "dry_run": True},
    )

    result = run_caldav_sync(config, dry_run=True)
    assert result["dry_run"] is True
