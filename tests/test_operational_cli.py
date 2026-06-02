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
    def fake_post_to_ics(_config, _post_id, *, verbose=False):
        raise RuntimeError("Refusing to export 1 entries with status=needs_review.")

    monkeypatch.setattr(
        cli.service,
        "post_to_ics",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("Refusing to export 1 entries with status=needs_review.")),
    )
    monkeypatch.setattr(cli, "_print_validation", lambda *_a, **_k: True)
    rc = cli.main(["post-to-ics", "--config", str(cfg_path), "--post-id", "7"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "Refusing to export 1 entries with status=needs_review" in out


def test_cli_commands_delegate_to_service_layer(monkeypatch, tmp_path, capsys):
    cfg = AppConfig(output_dir=str(tmp_path), error_dir=str(tmp_path / "err"), logs_dir=str(tmp_path / "logs"))
    cfg_path = tmp_path / "config.json"
    save_config(cfg, str(cfg_path))
    monkeypatch.setattr(cli, "_print_validation", lambda *_a, **_k: True)
    monkeypatch.setattr(cli, "_validate_update_today", lambda *_a, **_k: True)

    calls = []

    monkeypatch.setattr(cli.service, "fetch_post_payload", lambda _cfg, post_id: calls.append(("fetch", post_id)) or {"post_id": post_id, "post_content": ""})
    monkeypatch.setattr(
        cli.service,
        "parse_post",
        lambda _cfg, post_id: calls.append(("parse", post_id))
        or type("Parsed", (), {"to_dict": lambda self, include_ignored=True: {"post_id": post_id, "entries": []}})(),
    )
    entries_file = tmp_path / "entries.json"
    entries_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(cli.service, "export_ics_from_json_file", lambda _cfg, path: calls.append(("export", str(path))) or "BEGIN:VCALENDAR")
    monkeypatch.setattr(cli.service, "run_today_pipeline", lambda _cfg: calls.append(("run_today", None)) or {"post_id": 1, "entries": []})
    monkeypatch.setattr(
        cli.service,
        "post_to_ics",
        lambda _cfg, post_id, verbose=False: calls.append(("post_to_ics", post_id, verbose))
        or {
            "post_id": post_id,
            "title": "T",
            "post_date": "2026-01-01",
            "output_file": str(tmp_path / "x.ics"),
            "entry_count": 1,
            "ignored_block_count": 0,
            "warning_count": 0,
            "warnings": [],
            "parsed_entry_count": 1,
        },
    )
    monkeypatch.setattr(cli.service, "publish_ics", lambda _cfg, days, verbose=False: calls.append(("publish", days, verbose)) or {"items": [], "published_count": 0})
    monkeypatch.setattr(cli.service, "update_today_ics", lambda _cfg, post_id=None, mode="copy": calls.append(("today", post_id, mode)) or {"today": "2026-01-01", "source_file": "a.ics", "target_file": "today.ics", "mode": mode})
    monkeypatch.setattr(cli.service, "run_ics_service", lambda config, days, interval_seconds, host, port, verbose=False: calls.append(("service", days, interval_seconds, host, port, verbose)))

    assert cli.main(["fetch-post", "--config", str(cfg_path), "--post-id", "7"]) == 0
    assert cli.main(["parse-post", "--config", str(cfg_path), "--post-id", "8"]) == 0
    assert cli.main(["export-ics", "--config", str(cfg_path), "--entries-json", str(entries_file)]) == 0
    assert cli.main(["run-today", "--config", str(cfg_path)]) == 0
    assert cli.main(["post-to-ics", "--config", str(cfg_path), "--post-id", "9", "--verbose"]) == 0
    assert cli.main(["publish-ics", "--config", str(cfg_path), "--days", "2", "--verbose"]) == 0
    assert cli.main(["update-today-ics", "--config", str(cfg_path), "--post-id", "9", "--mode", "symlink"]) == 0
    assert cli.main(["run-ics-service", "--config", str(cfg_path), "--days", "3", "--interval", "4", "--host", "0.0.0.0", "--port", "5555", "--verbose"]) == 0

    assert ("fetch", 7) in calls
    assert ("parse", 8) in calls
    assert ("export", str(entries_file)) in calls
    assert ("run_today", None) in calls
    assert ("post_to_ics", 9, True) in calls
    assert ("publish", 2, True) in calls
    assert ("today", 9, "symlink") in calls
    assert ("service", 3, 4, "0.0.0.0", 5555, True) in calls


def test_cli_fetch_and_parse_require_post_id_without_silent_default(monkeypatch, tmp_path):
    cfg_path = tmp_path / "config.json"
    save_config(AppConfig(), str(cfg_path))
    monkeypatch.setattr(cli, "_print_validation", lambda *_a, **_k: True)
    monkeypatch.setattr(cli.service, "fetch_post_payload", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not fetch")))
    monkeypatch.setattr(cli.service, "parse_post", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not parse")))

    assert cli.main(["fetch-post", "--config", str(cfg_path)]) == 2
    assert cli.main(["parse-post", "--config", str(cfg_path)]) == 2
