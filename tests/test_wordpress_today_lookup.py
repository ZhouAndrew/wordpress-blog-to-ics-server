from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import today_local_date
from wp_log_parser.wordpress import find_today_post_id_rest, find_today_post_id_wpcli


class _Response:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_find_today_post_id_wpcli_uses_local_date_range(monkeypatch, tmp_path):
    monkeypatch.setattr("wp_log_parser.wordpress.shutil.which", lambda _cmd: "/usr/bin/wp")
    monkeypatch.setattr("wp_log_parser.wordpress.Path.exists", lambda self: str(self) == str(tmp_path))

    seen = {}

    def _fake_run(cmd, **_kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps([{"ID": 77, "post_date": "2026-04-11 09:00:00"}]), stderr="")

    monkeypatch.setattr("wp_log_parser.wordpress.subprocess.run", _fake_run)

    post_id = find_today_post_id_wpcli(str(tmp_path), "2026-04-11", "wp")

    assert post_id == 77
    assert "--date_query=after=2026-04-11 00:00:00,before=2026-04-11 23:59:59,inclusive=1" in seen["cmd"]
    assert "--fields=ID,post_title,post_date,post_modified_gmt,post_status" in seen["cmd"]


def test_find_today_post_id_wpcli_sorts_candidates_by_date_then_id(monkeypatch, tmp_path):
    monkeypatch.setattr("wp_log_parser.wordpress.shutil.which", lambda _cmd: "/usr/bin/wp")
    monkeypatch.setattr("wp_log_parser.wordpress.Path.exists", lambda self: str(self) == str(tmp_path))

    def _fake_run(cmd, **_kwargs):
        rows = [
            {"ID": 10, "post_date": "2026-04-11 12:00:00"},
            {"ID": 12, "post_date": "2026-04-11 12:00:00"},
            {"ID": 99, "post_date": "2026-04-11 08:00:00"},
        ]
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr="")

    monkeypatch.setattr("wp_log_parser.wordpress.subprocess.run", _fake_run)

    assert find_today_post_id_wpcli(str(tmp_path), "2026-04-11", "wp") == 12


def test_find_today_post_id_rest_uses_local_date_range(monkeypatch):
    seen = {}

    def _fake_get(endpoint, **_kwargs):
        seen["endpoint"] = endpoint
        return _Response(200, [{"id": 88, "date": "2026-04-12T09:00:00"}])

    monkeypatch.setattr("requests.get", _fake_get)

    post_id = find_today_post_id_rest("https://example.test", "u", "p", "2026-04-12", True)

    assert post_id == 88
    assert "after=2026-04-12T00:00:00" in seen["endpoint"]
    assert "before=2026-04-12T23:59:59" in seen["endpoint"]
    assert "orderby=date&order=desc&per_page=100" in seen["endpoint"]


def test_find_today_post_id_rest_sorts_candidates_by_date_then_id(monkeypatch):
    def _fake_get(endpoint, **_kwargs):
        return _Response(
            200,
            [
                {"id": 200, "date": "2026-04-12T10:00:00"},
                {"id": 201, "date": "2026-04-12T10:00:00"},
                {"id": 999, "date": "2026-04-12T08:00:00"},
            ],
        )

    monkeypatch.setattr("requests.get", _fake_get)

    assert find_today_post_id_rest("https://example.test", "u", "p", "2026-04-12", True) == 201


def test_today_local_date_uses_config_timezone(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 12, 0, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr("wp_log_parser.fetcher.datetime", FixedDatetime)

    assert today_local_date(AppConfig(timezone="America/Los_Angeles")) == "2026-04-11"
    assert today_local_date(AppConfig(timezone="Asia/Tokyo")) == "2026-04-12"
