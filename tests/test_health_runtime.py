from __future__ import annotations

from types import SimpleNamespace

from wp_log_parser import cli
from wp_log_parser.config import AppConfig
from wp_log_parser.health import _item, run_caldav_write_test, run_health_check


def _mk_post(post_id: int, post_date: str = "2026-01-01", content: str = "<p>07:30 test</p>"):
    return SimpleNamespace(post_id=post_id, title=f"P{post_id}", post_date=post_date, post_content=content)


def test_item_details_is_always_dict():
    assert isinstance(_item("ok", "x")["details"], dict)


def test_wordpress_list_failure_returns_error(monkeypatch):
    cfg = AppConfig()
    monkeypatch.setattr("wp_log_parser.health.list_posts", lambda c: (_ for _ in ()).throw(RuntimeError("boom")))
    report = run_health_check(cfg, full=True)
    assert any(i["status"] == "error" for i in report["wordpress_runtime"])


def test_latest_post_selected(monkeypatch):
    cfg = AppConfig()
    monkeypatch.setattr("wp_log_parser.health.list_posts", lambda c: [{"id": 1, "date": "2026-01-01"}, {"id": 2, "date": "2026-01-02"}])
    seen = {"id": None}
    monkeypatch.setattr("wp_log_parser.health.fetch_post", lambda c, pid: seen.__setitem__("id", pid) or _mk_post(pid, "2026-01-02"))
    monkeypatch.setattr("wp_log_parser.health.parse_post_content", lambda *a, **k: SimpleNamespace(entries=[SimpleNamespace(to_dict=lambda: {"start_dt": "x"})], ignored_blocks=[], warnings=[]))
    monkeypatch.setattr("wp_log_parser.health.generate_ics", lambda *a, **k: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    run_health_check(cfg, full=True)
    assert seen["id"] == 2


def test_zero_entries_parser_warning_and_ics_warning(monkeypatch):
    cfg = AppConfig()
    monkeypatch.setattr("wp_log_parser.health.list_posts", lambda c: [{"id": 1, "date": "2026-01-01"}])
    monkeypatch.setattr("wp_log_parser.health.fetch_post", lambda c, pid: _mk_post(pid))
    monkeypatch.setattr("wp_log_parser.health.parse_post_content", lambda *a, **k: SimpleNamespace(entries=[], ignored_blocks=[], warnings=[]))
    report = run_health_check(cfg, full=True)
    assert report["parser_runtime"][0]["status"] == "warning"
    assert report["ics_runtime"][0]["status"] == "warning"


def test_caldav_missing_config_warning_or_skipped():
    cfg = AppConfig(caldav_url="", caldav_username="", caldav_password="")
    report = run_health_check(cfg, full=False)
    assert report["caldav_runtime"][0]["status"] in {"warning", "skipped"}


def test_caldav_connectivity_success(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/caldav", caldav_username="u", caldav_password="p")
    monkeypatch.setattr("wp_log_parser.health._request_status", lambda *a, **k: 200)
    report = run_health_check(cfg, full=False)
    assert report["caldav_runtime"][0]["status"] == "ok"


def test_write_test_requested_with_invalid_config_not_not_requested():
    cfg = AppConfig(caldav_url="", caldav_username="", caldav_password="")
    report = run_health_check(cfg, full=False, test_caldav_write=True)
    assert "not requested" not in report["caldav_write_test"][0]["message"]


def test_disposable_write_put_failure_returns_error(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")
    monkeypatch.setattr("wp_log_parser.health._request_status", lambda method, *a, **k: 500 if method == "PUT" else 204)
    item = run_caldav_write_test(cfg)
    assert item["status"] == "error"


def test_disposable_write_get_unsupported_still_deletes(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")
    calls = []
    monkeypatch.setattr(
        "wp_log_parser.health._request_status",
        lambda method, *a, **k: calls.append(method) or (201 if method == "PUT" else 405 if method == "GET" else 204),
    )
    item = run_caldav_write_test(cfg)
    assert calls == ["PUT", "GET", "DELETE"]
    assert item["status"] == "warning"
    assert item["details"]["delete_status"] == 204


def test_disposable_write_get_500_not_ok_and_still_deletes(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")
    calls = []
    monkeypatch.setattr(
        "wp_log_parser.health._request_status",
        lambda method, *a, **k: calls.append(method) or (201 if method == "PUT" else 500 if method == "GET" else 204),
    )
    item = run_caldav_write_test(cfg)
    assert calls == ["PUT", "GET", "DELETE"]
    assert item["status"] != "ok"
    assert item["details"]["delete_status"] == 204


def test_disposable_write_delete_cleanup_failure_warning(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")
    monkeypatch.setattr("wp_log_parser.health._request_status", lambda method, *a, **k: 201 if method == "PUT" else 200 if method == "GET" else 500)
    item = run_caldav_write_test(cfg)
    assert item["status"] in {"warning", "error"}
    assert "resource_path" in item["details"]
    assert item["details"]["delete_status"] == 500


def test_disposable_write_get_exception_still_deletes(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")
    calls = []

    def _mock_status(method, *a, **k):
        calls.append(method)
        if method == "PUT":
            return 201
        if method == "GET":
            raise RuntimeError("get exploded")
        return 204

    monkeypatch.setattr("wp_log_parser.health._request_status", _mock_status)
    item = run_caldav_write_test(cfg)
    assert calls == ["PUT", "GET", "DELETE"]
    assert item["status"] != "ok"
    assert "get_error" in item["details"]
    assert item["details"]["delete_status"] == 204


def test_disposable_write_delete_exception(monkeypatch):
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")

    def _mock_status(method, *a, **k):
        if method == "PUT":
            return 201
        if method == "GET":
            return 200
        raise RuntimeError("delete exploded")

    monkeypatch.setattr("wp_log_parser.health._request_status", _mock_status)
    item = run_caldav_write_test(cfg)
    assert item["status"] in {"warning", "error"}
    assert "delete_error" in item["details"]
    assert "resource_path" in item["details"]


def test_request_status_raises_when_requests_unavailable(monkeypatch):
    from wp_log_parser import health

    monkeypatch.setattr(health, "_requests", None)
    cfg = AppConfig(caldav_url="https://x/c", caldav_username="u", caldav_password="p")
    try:
        health._request_status("OPTIONS", cfg.caldav_url, cfg)
    except RuntimeError as exc:
        assert "requests package is required" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_doctor_full_require_caldav_fails_when_missing(monkeypatch):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig(caldav_url="", caldav_username="", caldav_password=""))
    assert cli.main(["doctor", "--full", "--require-caldav", "--config", "./config.json"]) == 1


def test_app_boot_runs_health_before_menu(monkeypatch):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    seen = {"health": 0}
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: seen.__setitem__("health", seen["health"] + 1) or {"config": [], "environment": [], "wordpress_runtime": [], "parser_runtime": [], "ics_runtime": [], "caldav_runtime": [], "caldav_write_test": [], "logs": []})
    inputs = iter(["n", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert seen["health"] >= 1


def test_real_sync_requires_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(cli, "config_exists", lambda _path: True)
    monkeypatch.setattr(cli, "load_config", lambda _path: AppConfig())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(cli, "run_health_check", lambda *a, **k: {"config": [], "environment": [], "wordpress_runtime": [], "parser_runtime": [], "ics_runtime": [], "caldav_runtime": [], "caldav_write_test": [], "logs": []})
    calls = []
    monkeypatch.setattr(cli, "run_caldav_sync", lambda config, dry_run=False: calls.append(dry_run) or {"dry_run": dry_run})
    inputs = iter(["n", "7", "0"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))
    assert cli.main(["app", "--config", "./config.json"]) == 0
    assert calls == []
    assert "CalDAV is not configured" in capsys.readouterr().out
