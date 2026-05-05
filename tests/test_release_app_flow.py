import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wp_log_parser import cli
from wp_log_parser.config import AppConfig, load_config, save_config


def test_repair_configuration_preserves_unrelated_existing_fields(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    existing = AppConfig(
        timezone="America/Chicago",
        output_dir=str(tmp_path / "out"),
        error_dir=str(tmp_path / "err"),
        logs_dir=str(tmp_path / "runtime-logs"),
        caldav_url="https://caldav.example/calendars/bob/home/",
        caldav_username="bob",
        caldav_password="keep-me",
        caldav_uid_domain="cal.example",
        caldav_index_path=str(tmp_path / "state" / "index.json"),
        custom_parsing_patterns=[
            {
                "name": "todo",
                "regex": r"^\s*(?P<start>\d{1,2}:\d{2})\s+TODO\s+(?P<summary>.*)$",
                "kind": "point",
            }
        ],
    )
    save_config(existing, str(config_path))

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    monkeypatch.setattr("wp_log_parser.setup_wizard.prompt_executable", lambda _l, _e, default: default)
    monkeypatch.setattr("wp_log_parser.setup_wizard.prompt_existing_path", lambda _l, _e, default: default)
    monkeypatch.setattr("wp_log_parser.setup_wizard.prompt_directory", lambda _l, _e, default: default)
    ok = lambda name: type("R", (), {"ok": True, "name": name, "message": "ok", "details": ""})()
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_dependencies", lambda: [])
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_python_path", lambda _p: ok("python"))
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_output_dir", lambda _p: ok("dir"))
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_wp_cli", lambda _p: ok("wp"))
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_wordpress_path", lambda _p: ok("wp_path"))
    monkeypatch.setattr("getpass.getpass", lambda _=None: "")

    inputs = iter(["2", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "y", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    assert cli.main(["app", "--config", str(config_path)]) == 0

    updated = load_config(str(config_path))
    assert updated.timezone == existing.timezone
    assert updated.logs_dir == existing.logs_dir
    assert updated.caldav_url == existing.caldav_url
    assert updated.caldav_username == existing.caldav_username
    assert updated.caldav_password == existing.caldav_password
    assert updated.caldav_index_path == existing.caldav_index_path
    assert updated.custom_parsing_patterns == existing.custom_parsing_patterns


def test_blocks_dry_run_when_caldav_url_missing(monkeypatch, capsys):
    cfg = AppConfig(caldav_url="", caldav_username="", caldav_password="")
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    monkeypatch.setattr(cli, "run_caldav_sync", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not run")))
    inputs = iter(["n", "6", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert "CalDAV is not configured" in capsys.readouterr().out


def test_recent_posts_newest_first():
    posts = [{"date": "2026-01-01"}, {"date": "2026-01-03"}, {"date": "2026-01-02"}]
    out = cli.list_posts.__globals__["list_posts_wpcli"].__globals__["sort_and_limit_posts"](posts)
    assert [p["date"] for p in out] == ["2026-01-03", "2026-01-02", "2026-01-01"]


def test_preview_requires_selection_not_first_post(monkeypatch):
    cfg = AppConfig()
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    monkeypatch.setattr(cli, "list_posts", lambda _c: [
        {"id": 1, "title": "Hello world!", "date": "2026-01-01", "status": "publish"},
        {"id": 2, "title": "Diary", "date": "2026-01-02", "status": "publish"},
    ])
    calls = []
    class P: post_content = ""; post_date = "2026-01-02"
    monkeypatch.setattr(cli, "fetch_post", lambda _c, pid: calls.append(pid) or P())
    monkeypatch.setattr(cli, "parse_post_content", lambda *a, **k: type("X", (), {"entries": [], "ignored_blocks": [], "warnings": [], "to_dict": lambda self, include_ignored=True: {}})())
    inputs = iter(["n", "5", "2", "n", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert calls == [2]


def test_update_today_ics_calls_correct_signature(monkeypatch, capsys):
    cfg = AppConfig()
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    called = {}
    monkeypatch.setattr(cli, "generate_today_ics", lambda output_dir, timezone, preferred_post_id=None, mode="copy": called.update({"output_dir": output_dir, "timezone": timezone, "preferred_post_id": preferred_post_id, "mode": mode}) or "/tmp/today.ics")
    inputs = iter(["n", "11", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert called["output_dir"] == cfg.output_dir
    assert called["timezone"] == cfg.timezone
    assert called["mode"] == "copy"
    assert "Updated today.ics" in capsys.readouterr().out


def test_local_publish_menu_calls_publish_once_with_days(monkeypatch):
    cfg = AppConfig()
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    called = {}
    monkeypatch.setattr(cli, "publish_once", lambda config, days, verbose=False: called.update({"days": days, "verbose": verbose}) or {"ok": True})
    inputs = iter(["n", "10", "3", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert called == {"days": 3, "verbose": True}


def test_health_summary_warning_for_parser_warning(capsys):
    cli._print_health_summary(AppConfig(), {"wordpress_runtime": [{"status": "ok"}], "parser_runtime": [{"status": "warning"}], "ics_runtime": [{"status": "ok"}]}, False)
    out = capsys.readouterr().out
    assert "Parser: warning" in out


def test_readme_keeps_license_debugging_and_getting_started():
    text = open("README.md", encoding="utf-8").read()
    assert "Pre-alpha / internal validation build" in text
    assert "## Before v0.1.0-alpha" in text
    assert "## License" in text
    assert "## Debugging" in text
    assert "## Getting Started Guide" in text


def test_service_menu_calls_run_service_loop_with_interval_seconds(monkeypatch):
    cfg = AppConfig()
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    called = {}
    monkeypatch.setattr(
        cli,
        "run_service_loop",
        lambda config, days, interval_seconds, host, port, verbose=False: called.update(
            {"days": days, "interval_seconds": interval_seconds, "host": host, "port": port, "verbose": verbose}
        ),
    )
    inputs = iter(["n", "12", "", "", "120", "5", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert called["interval_seconds"] == 120


def test_today_ics_missing_source_message(monkeypatch, capsys):
    cfg = AppConfig()
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    monkeypatch.setattr(cli, "generate_today_ics", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("missing")))
    inputs = iter(["n", "11", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert "No ICS file for today exists yet. Generate local ICS files first." in capsys.readouterr().out


def test_caldav_incomplete_message(monkeypatch, capsys):
    cfg = AppConfig(caldav_url="https://cal.example", caldav_username="", caldav_password="")
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    inputs = iter(["n", "6", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert "CalDAV configuration is incomplete." in capsys.readouterr().out


def test_ctrl_c_in_app_is_clean(monkeypatch, capsys):
    cfg = AppConfig()
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    calls = iter(["n", KeyboardInterrupt(), "0"])
    def _in(_p=""):
        v = next(calls)
        if isinstance(v, BaseException):
            raise v
        return v
    monkeypatch.setattr("builtins.input", _in)
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert "Operation cancelled." in capsys.readouterr().out


def test_real_sync_requires_dry_run_when_caldav_configured(monkeypatch, capsys):
    cfg = AppConfig(caldav_url="https://cal.example", caldav_username="alice", caldav_password="secret")
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    calls = []
    monkeypatch.setattr(cli, "run_caldav_sync", lambda config, dry_run=False: calls.append(dry_run) or {"dry_run": dry_run})
    inputs = iter(["n", "7", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert calls == []
    assert "Real sync blocked" in capsys.readouterr().out


def test_dry_run_then_real_sync_allowed(monkeypatch, tmp_path):
    cfg = AppConfig(
        caldav_url="https://cal.example",
        caldav_username="alice",
        caldav_password="secret",
        logs_dir=str(tmp_path / "logs"),
    )
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    calls = []
    monkeypatch.setattr(
        cli,
        "run_caldav_sync",
        lambda config, dry_run=False: calls.append(dry_run) or {"dry_run": dry_run, "changed_posts": 1, "index_path": "./output/caldav_sync_index.json"},
    )
    inputs = iter(["n", "6", "7", "YES", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert calls == [True, False]
    assert (Path(cfg.logs_dir) / "caldav_dry_run_marker.json").exists()


def test_restart_with_no_marker_denied(monkeypatch, capsys, tmp_path):
    cfg = AppConfig(
        caldav_url="https://cal.example",
        caldav_username="alice",
        caldav_password="secret",
        logs_dir=str(tmp_path / "logs"),
    )
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    called = []
    monkeypatch.setattr(cli, "run_caldav_sync", lambda config, dry_run=False: called.append(dry_run) or {"dry_run": dry_run})
    inputs = iter(["n", "7", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert called == []
    out = capsys.readouterr().out
    assert "Real sync blocked" in out
    assert "run option 6" in out.lower()


def test_stale_or_incompatible_marker_denied(monkeypatch, capsys, tmp_path):
    cfg = AppConfig(
        caldav_url="https://cal.example",
        caldav_username="alice",
        caldav_password="secret",
        logs_dir=str(tmp_path / "logs"),
    )
    marker = Path(cfg.logs_dir) / "caldav_dry_run_marker.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "kind": "caldav_dry_run_success",
                "created_at_utc": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "config_fingerprint": "mismatch",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: cfg)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"wordpress_runtime": [], "parser_runtime": [], "ics_runtime": []})
    called = []
    monkeypatch.setattr(cli, "run_caldav_sync", lambda config, dry_run=False: called.append(dry_run) or {"dry_run": dry_run})
    inputs = iter(["n", "7", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert called == []
    out = capsys.readouterr().out
    assert "Real sync blocked" in out
    assert "stale" in out


def test_dry_run_marker_incompatible_on_timezone_change(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path / "logs"), timezone="UTC")
    cli._write_dry_run_marker(cfg, {"changed_posts": 1, "index_path": "./output/index.json"})
    changed = AppConfig(logs_dir=cfg.logs_dir, timezone="America/Chicago")
    ok, msg = cli._dry_run_marker_compatibility(changed)
    assert not ok
    assert "incompatible" in msg.lower()


def test_dry_run_marker_incompatible_on_custom_pattern_change(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path / "logs"), custom_parsing_patterns=[{"name": "x", "regex": r"^\\d", "kind": "point"}])
    cli._write_dry_run_marker(cfg, {"changed_posts": 1, "index_path": "./output/index.json"})
    changed = AppConfig(logs_dir=cfg.logs_dir, custom_parsing_patterns=[{"name": "y", "regex": r"^\\d", "kind": "point"}])
    ok, msg = cli._dry_run_marker_compatibility(changed)
    assert not ok
    assert "incompatible" in msg.lower()


def test_dry_run_marker_incompatible_on_default_last_event_minutes_change(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path / "logs"), default_last_event_minutes=30)
    cli._write_dry_run_marker(cfg, {"changed_posts": 1, "index_path": "./output/index.json"})
    changed = AppConfig(logs_dir=cfg.logs_dir, default_last_event_minutes=45)
    ok, msg = cli._dry_run_marker_compatibility(changed)
    assert not ok
    assert "incompatible" in msg.lower()


def test_dry_run_marker_incompatible_on_caldav_url_change(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path / "logs"), caldav_url="https://a.example/caldav/")
    cli._write_dry_run_marker(cfg, {"changed_posts": 1, "index_path": "./output/index.json"})
    changed = AppConfig(logs_dir=cfg.logs_dir, caldav_url="https://b.example/caldav/")
    ok, msg = cli._dry_run_marker_compatibility(changed)
    assert not ok
    assert "incompatible" in msg.lower()


def test_dry_run_marker_compatible_on_display_only_change(tmp_path):
    cfg = AppConfig(logs_dir=str(tmp_path / "logs"), post_selection_count=20)
    cli._write_dry_run_marker(cfg, {"changed_posts": 1, "index_path": "./output/index.json"})
    changed = AppConfig(logs_dir=cfg.logs_dir, post_selection_count=99)
    ok, msg = cli._dry_run_marker_compatibility(changed)
    assert ok
    assert "ready" in msg.lower()
