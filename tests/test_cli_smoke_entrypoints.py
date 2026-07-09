from __future__ import annotations

from wp_log_parser import cli
from wp_log_parser.config import AppConfig


def _stub_runtime(monkeypatch):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig())
    monkeypatch.setattr(cli, "_print_validation", lambda *_a, **_k: True)


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

    monkeypatch.setattr(cli, "fetch_post", lambda *_a, **_k: type("P", (), {"post_id": 9, "post_date": "2026-05-01", "post_content": "", "title": "T"})())
    monkeypatch.setattr(cli, "normalize_post_date", lambda d: d)
    monkeypatch.setattr(
        cli,
        "parse_post_content",
        lambda *_a, **_k: type("X", (), {"entries": [type("E", (), {"status": "ready"})()], "ignored_blocks": [], "warnings": []})(),
    )
    monkeypatch.setattr(cli, "attach_source_metadata", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "write_post_ics", lambda *_a, **_k: "/tmp/out.ics")
    publish_calls = []
    monkeypatch.setattr(
        cli,
        "publish_once",
        lambda _config, days, **_k: publish_calls.append(days) or {"ok": True, "items": [], "published_count": 0},
    )
    monkeypatch.setattr(cli, "run_service_loop", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "today_date_str", lambda _tz: "2026-05-24")
    monkeypatch.setattr(cli, "find_today_ics_candidates", lambda *_a, **_k: [])
    monkeypatch.setattr(cli, "select_today_ics", lambda *_a, **_k: type("S", (), {"name": "2026-05-24_post_9_demo.ics"})())
    monkeypatch.setattr(cli, "generate_today_ics", lambda *_a, **_k: type("T", (), {"name": "today.ics"})())

    assert cli.main(["post-to-ics", "--config", "./config.json", "--post-id", "9"]) == 0
    assert cli.main(["publish-ics", "--config", "./config.json"]) == 0
    assert publish_calls[-1] == 7
    assert cli.main(["publish-ics", "--config", "./config.json", "--days", "1"]) == 0
    assert publish_calls[-1] == 1
    assert cli.main(["update-today-ics", "--config", "./config.json"]) == 0
    assert cli.main(["run-ics-service", "--config", "./config.json", "--days", "1", "--interval", "1"]) == 0
