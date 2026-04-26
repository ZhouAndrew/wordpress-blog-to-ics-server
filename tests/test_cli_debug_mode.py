from __future__ import annotations

import json
from pathlib import Path

from wp_log_parser import cli
from wp_log_parser.config import AppConfig


def test_sync_caldav_debug_writes_last_run_and_redacts_secrets(tmp_path, monkeypatch, capsys) -> None:
    config = AppConfig(error_dir=str(tmp_path), app_password="wp-secret", caldav_password="caldav-secret")

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)

    def fake_sync(_config, dry_run=False, debug_events=None):
        if debug_events is not None:
            debug_events.append(
                {
                    "operation": "create",
                    "post_id": 101,
                    "uid": "uid-1",
                    "resource_path": "uid-1.ics",
                    "status_before": None,
                    "status_after": "confirmed",
                    "sequence_before": None,
                    "sequence_after": 0,
                    "reason": "new event",
                }
            )
        return {
            "created": 1,
            "updated": 0,
            "deleted": 0,
            "cancelled": 0,
            "skipped": 0,
            "changed_posts": 1,
            "dry_run": dry_run,
            "index_path": "./output/caldav_sync_index.json",
        }

    monkeypatch.setattr(cli, "run_caldav_sync", fake_sync)

    code = cli.main(["sync-caldav", "--config", "./config.json", "--debug"])
    out = capsys.readouterr().out

    assert code == 0
    assert "wp-secret" not in out
    assert "caldav-secret" not in out

    snapshot = Path(config.error_dir) / "last_run.json"
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["config"]["app_password"] == "***"
    assert payload["config"]["caldav_password"] == "***"
    assert payload["caldav_counts"]["created"] == 1
    assert payload["debug_operations"][0]["operation"] == "create"


def test_sync_caldav_failure_writes_debug_report(tmp_path, monkeypatch, capsys) -> None:
    config = AppConfig(error_dir=str(tmp_path))

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(cli, "run_caldav_sync", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("sync broke")))

    code = cli.main(["sync-caldav", "--config", "./config.json", "--debug"])
    out = capsys.readouterr().out

    assert code == 1
    assert "Debug report written to:" in out

    payload = json.loads((Path(config.error_dir) / "last_run.json").read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["error"]["type"] == "RuntimeError"
    assert "Traceback" in payload["error"]["traceback"]


def test_sync_caldav_dry_run_snapshot_marks_dry_run_true(tmp_path, monkeypatch) -> None:
    config = AppConfig(error_dir=str(tmp_path))

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(
        cli,
        "run_caldav_sync",
        lambda *_args, **_kwargs: {
            "created": 2,
            "updated": 0,
            "deleted": 0,
            "cancelled": 0,
            "skipped": 0,
            "changed_posts": 1,
            "dry_run": True,
            "index_path": "./output/caldav_sync_index.json",
        },
    )

    code = cli.main(["sync-caldav", "--config", "./config.json", "--dry-run"])

    assert code == 0
    payload = json.loads((Path(config.error_dir) / "last_run.json").read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["success"] is True


def test_successful_sync_caldav_does_not_fail_if_snapshot_write_fails(monkeypatch, capsys) -> None:
    config = AppConfig(error_dir="./errors")

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(
        cli,
        "run_caldav_sync",
        lambda *_args, **_kwargs: {
            "created": 1,
            "updated": 0,
            "deleted": 0,
            "cancelled": 0,
            "skipped": 0,
            "changed_posts": 1,
            "dry_run": False,
            "index_path": "./output/caldav_sync_index.json",
        },
    )
    monkeypatch.setattr(cli, "write_recent_run_snapshot", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("snapshot failed")))

    code = cli.main(["sync-caldav", "--config", "./config.json"])
    out = capsys.readouterr().out

    assert code == 0
    assert "[WARN] Failed to write run snapshot: snapshot failed" in out


def test_successful_run_today_does_not_fail_if_snapshot_write_fails(monkeypatch, capsys) -> None:
    config = AppConfig(error_dir="./errors")

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(
        cli,
        "run_today_pipeline",
        lambda _config: {"post_id": 10, "entries": [{"start_time": "07:45"}], "ignored_blocks": [], "ics_preview": "BEGIN:VCALENDAR"},
    )
    monkeypatch.setattr(cli, "write_recent_run_snapshot", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("snapshot failed")))

    code = cli.main(["run-today", "--config", "./config.json"])
    out = capsys.readouterr().out

    assert code == 0
    assert "[WARN] Failed to write run snapshot: snapshot failed" in out


def test_successful_post_to_ics_does_not_fail_if_snapshot_write_fails(monkeypatch, capsys, tmp_path) -> None:
    config = AppConfig(error_dir="./errors", output_dir=str(tmp_path))

    class _Post:
        post_id = 10
        title = "Daily"
        post_date = "2026-04-01 00:00:00"
        post_content = "<p>07:45 Breakfast</p>"

    class _Parsed:
        entries = [object()]
        ignored_blocks = []

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(cli, "fetch_post", lambda _config, _post_id: _Post())
    monkeypatch.setattr(cli, "normalize_post_date", lambda value: value)
    monkeypatch.setattr(cli, "parse_post_content", lambda *_args, **_kwargs: _Parsed())
    monkeypatch.setattr(cli, "write_post_ics", lambda *_args, **_kwargs: tmp_path / "out.ics")
    monkeypatch.setattr(cli, "write_recent_run_snapshot", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("snapshot failed")))

    code = cli.main(["post-to-ics", "--config", "./config.json", "--post-id", "10"])
    out = capsys.readouterr().out

    assert code == 0
    assert "[WARN] Failed to write run snapshot: snapshot failed" in out


def test_successful_publish_ics_does_not_fail_if_snapshot_write_fails(monkeypatch, capsys) -> None:
    config = AppConfig(error_dir="./errors")

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(
        cli,
        "publish_once",
        lambda *_args, **_kwargs: {"published_count": 1, "items": [{"post_id": 10}], "index_json": "./output/index.json"},
    )
    monkeypatch.setattr(cli, "write_recent_run_snapshot", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("snapshot failed")))

    code = cli.main(["publish-ics", "--config", "./config.json", "--days", "7"])
    out = capsys.readouterr().out

    assert code == 0
    assert "[WARN] Failed to write run snapshot: snapshot failed" in out


def test_failed_sync_still_returns_original_failure_when_snapshot_write_fails(monkeypatch, capsys) -> None:
    config = AppConfig(error_dir="./errors")

    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False: True)
    monkeypatch.setattr(cli, "run_caldav_sync", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("sync broke")))
    monkeypatch.setattr(cli, "write_recent_run_snapshot", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("snapshot failed")))

    code = cli.main(["sync-caldav", "--config", "./config.json", "--debug"])
    out = capsys.readouterr().out

    assert code == 1
    assert "[WARN] Failed to write debug report: snapshot failed" in out
    assert "[ERROR] sync broke" in out
