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
    assert "[WARN] Timeline warnings: 1" in out
    assert "overlap found" in out


def test_validate_config_wpcli_exit_success_when_selected_mode_checks_pass(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "config.json"
    out = tmp_path / "out"
    err = tmp_path / "err"
    logs = tmp_path / "logs"
    out.mkdir()
    err.mkdir()
    logs.mkdir()
    wp_root = tmp_path / "wp"
    wp_root.mkdir()
    (wp_root / "wp-config.php").write_text("<?php", encoding="utf-8")
    save_config(AppConfig(output_dir=str(out), error_dir=str(err), logs_dir=str(logs), wp_path=str(wp_root)), str(cfg_path))
    monkeypatch.setattr(
        cli,
        "validate_wp_cli",
        lambda _path: type("R", (), {"ok": True, "name": "wp_cli", "message": "ok"})(),
    )

    rc = cli.main(["validate-config", "--config", str(cfg_path)])

    assert rc == 0
    assert "[OK] wp_cli" in capsys.readouterr().out


def test_validate_config_rest_exit_failure_for_invalid_credentials(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "config.json"
    out = tmp_path / "out"
    err = tmp_path / "err"
    logs = tmp_path / "logs"
    out.mkdir()
    err.mkdir()
    logs.mkdir()
    save_config(
        AppConfig(
            wordpress_mode="rest",
            base_url="https://wp.example",
            username="alice",
            app_password="wrong",
            output_dir=str(out),
            error_dir=str(err),
            logs_dir=str(logs),
        ),
        str(cfg_path),
    )
    monkeypatch.setattr(
        cli,
        "validate_rest_credentials",
        lambda *_args: type(
            "R",
            (),
            {"ok": False, "name": "rest", "message": "REST authentication failed; check app_password"},
        )(),
    )

    rc = cli.main(["validate-config", "--config", str(cfg_path)])

    out_text = capsys.readouterr().out
    assert rc == 1
    assert "[ERROR] rest: REST authentication failed; check app_password" in out_text


def test_validate_config_reports_load_error_for_unknown_key(tmp_path, capsys):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"wordpress_mode": "wpcli", "extra": "nope"}), encoding="utf-8")

    rc = cli.main(["validate-config", "--config", str(cfg_path)])

    assert rc == 2
    assert "Unknown config key" in capsys.readouterr().out
