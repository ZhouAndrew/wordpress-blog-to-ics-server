from __future__ import annotations

from wp_log_parser import cli
from wp_log_parser.config import AppConfig


def _stub_runtime(monkeypatch):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig())
    monkeypatch.setattr(cli, "_print_validation", lambda *_a, **_k: True)
    monkeypatch.setattr(cli, "_validate_update_today", lambda *_a, **_k: True)


def test_top_level_help_exits_zero(capsys):
    try:
        cli.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "wp_log_parser" in out
    assert "post-to-ics" in out


def test_command_help_paths_exits_zero(capsys):
    for command in ("post-to-ics", "publish-ics", "update-today-ics", "run-ics-service"):
        try:
            cli.main([command, "--help"])
        except SystemExit as exc:
            assert exc.code == 0
    out = capsys.readouterr().out
    assert "--config" in out


def _assert_system_exit_code(argv, expected):
    try:
        cli.main(argv)
    except SystemExit as exc:
        assert exc.code == expected
    else:
        assert False, f"Expected SystemExit({expected}) for argv={argv}"


def test_required_usage_paths_return_error_codes(monkeypatch):
    _stub_runtime(monkeypatch)

    # post-to-ics requires --post-id
    _assert_system_exit_code(["post-to-ics", "--config", "./config.json"], 2)

    # fetch/parse require exactly one of --post-id or --select-post-id
    assert cli.main(["fetch-post", "--config", "./config.json"]) == 2
    assert cli.main(["parse-post", "--config", "./config.json"]) == 2


def test_smoke_entry_points_dispatch_without_wordpress(monkeypatch):
    _stub_runtime(monkeypatch)

    monkeypatch.setattr(
        cli.service,
        "post_to_ics",
        lambda *_a, **_k: {
            "post_id": 9,
            "title": "T",
            "post_date": "2026-05-01",
            "output_file": "/tmp/out.ics",
            "entry_count": 1,
            "ignored_block_count": 0,
            "warning_count": 0,
            "warnings": [],
            "parsed_entry_count": 1,
        },
    )
    monkeypatch.setattr(cli.service, "publish_ics", lambda *_a, **_k: {"ok": True, "items": [], "published_count": 0})
    monkeypatch.setattr(
        cli.service,
        "update_today_ics",
        lambda *_a, **_k: {
            "today": "2026-05-24",
            "source_file": "2026-05-24_post_9_demo.ics",
            "target_file": "today.ics",
            "mode": "copy",
        },
    )
    monkeypatch.setattr(cli.service, "run_ics_service", lambda *_a, **_k: None)

    assert cli.main(["post-to-ics", "--config", "./config.json", "--post-id", "9"]) == 0
    assert cli.main(["publish-ics", "--config", "./config.json", "--days", "1"]) == 0
    assert cli.main(["update-today-ics", "--config", "./config.json"]) == 0
    assert cli.main(["run-ics-service", "--config", "./config.json", "--days", "1", "--interval", "1"]) == 0
