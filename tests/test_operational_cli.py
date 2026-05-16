from __future__ import annotations

import json

import pytest

from wp_log_parser import cli
from wp_log_parser.config import AppConfig, save_config
from wp_log_parser.operations import write_runtime_log


def test_config_get_set(tmp_path, capsys):
    cfg_path = tmp_path / "config.json"
    save_config(AppConfig(), str(cfg_path))
    assert cli.main(["config", "--config", str(cfg_path), "set", "timezone", "Asia/Seoul"]) == 0
    assert cli.main(["config", "--config", str(cfg_path), "get", "timezone"]) == 0
    assert "Asia/Seoul" in capsys.readouterr().out


@pytest.mark.parametrize(
    "key,value",
    [
        ("wordpress_mode", "bad"),
        ("log_format", "bad"),
        ("caldav_deletion_mode", "bad"),
        ("timezone", "Nope/Nowhere"),
        ("default_last_event_minutes", "-1"),
        ("post_selection_count", "999"),
        ("custom_parsing_patterns", "[]"),
    ],
)
def test_config_set_invalid_values(tmp_path, key, value):
    cfg_path = tmp_path / "config.json"
    save_config(AppConfig(), str(cfg_path))
    assert cli.main(["config", "--config", str(cfg_path), "set", key, value]) == 2


def test_doctor_default_and_require_caldav(monkeypatch):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig())
    monkeypatch.setattr(cli, "_print_validation", lambda _config, require_caldav=False, include_caldav=True: True)
    monkeypatch.setattr(cli, "validate_caldav_config", lambda *args, **kwargs: type("R", (), {"ok": False, "name": "caldav", "message": "missing"})())
    assert cli.main(["doctor", "--config", "./config.json"]) == 0
    assert cli.main(["doctor", "--config", "./config.json", "--require-caldav"]) == 1


def test_runtime_log_appends_jsonl(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path))
    p = write_runtime_log(cfg, "phase1", "one")
    write_runtime_log(cfg, "phase2", "two")
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["phase"] == "phase1"
    assert json.loads(lines[1])["phase"] == "phase2"


def test_runtime_log_redacts_secrets(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path))
    p = write_runtime_log(cfg, "phase", "msg", {"password": "abc", "note": "ok"})
    row = json.loads(p.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["details"]["password"] == "***"
    assert row["details"]["note"] == "ok"


def test_app_command_dispatch_tty(monkeypatch):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["app", "--config", "./config.json"]) == 2


def test_post_to_ics_surfaces_overlap_warning_and_blocks_on_error_mode(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "config.json"
    save_config(
        AppConfig(
            output_dir=str(tmp_path / "out"),
            error_dir=str(tmp_path / "err"),
            logs_dir=str(tmp_path / "logs"),
            overlap_policy="needs_review",
            review_entry_export_mode="error",
        ),
        str(cfg_path),
    )
    monkeypatch.setattr(cli, "fetch_post", lambda _c, _id: type("P", (), {"post_id": 7, "post_date": "2026-04-11", "post_content": "", "title": "T"})())
    monkeypatch.setattr(
        cli,
        "parse_post_content",
        lambda *_a, **_k: type(
            "X",
            (),
            {
                "entries": [type("E", (), {"status": "needs_review"})()],
                "ignored_blocks": [],
                "warnings": [type("W", (), {"reason": "overlap", "message": "overlap found"})()],
            },
        )(),
    )
    monkeypatch.setattr(cli, "attach_source_metadata", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_print_validation", lambda *_a, **_k: True)
    rc = cli.main(["post-to-ics", "--config", str(cfg_path), "--post-id", "7"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "[WARN] Timeline warnings: 1" in out
    assert "overlap found" in out
