from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from wp_log_parser.config import AppConfig
from wp_log_parser.exceptions import AuthenticationFailedError, MalformedResponseError, PostNotFoundError
from wp_log_parser.fetcher import PostData, fetch_post, find_today_post_id


class _Response:
    def __init__(self, status_code: int, payload=object(), json_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def _wpcli_config(tmp_path) -> AppConfig:
    return AppConfig(wordpress_mode="wpcli", wp_cli_path="wp", wp_path=str(tmp_path))


def _rest_config() -> AppConfig:
    return AppConfig(wordpress_mode="rest", base_url="https://example.test", username="u", app_password="p")


def _stub_wpcli_environment(monkeypatch, tmp_path, proc):
    monkeypatch.setattr("wp_log_parser.fetcher.shutil.which", lambda _cmd: "/usr/bin/wp")
    monkeypatch.setattr("wp_log_parser.fetcher.Path.exists", lambda self: str(self) == str(tmp_path))
    monkeypatch.setattr("wp_log_parser.fetcher.subprocess.run", lambda *_args, **_kwargs: proc)


def test_fetch_post_wpcli_success_returns_structured_post_data(monkeypatch, tmp_path):
    payload = {
        "ID": "123",
        "post_title": "Daily Log",
        "post_date": "2026-04-11 09:00:00",
        "post_content": "<p>07:45 Breakfast</p>",
        "post_status": "publish",
    }
    proc = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    _stub_wpcli_environment(monkeypatch, tmp_path, proc)

    post = fetch_post(_wpcli_config(tmp_path), 123)

    assert post == PostData(
        post_id=123,
        title="Daily Log",
        post_date="2026-04-11 09:00:00",
        post_content="<p>07:45 Breakfast</p>",
        status="publish",
    )


@pytest.mark.parametrize(
    "stderr,expected",
    [
        ("Error: Access denied for user", AuthenticationFailedError),
        ("Error: Invalid post ID.", PostNotFoundError),
        ("Error: corrupted output", MalformedResponseError),
    ],
)
def test_fetch_post_wpcli_maps_command_failures(monkeypatch, tmp_path, stderr, expected):
    proc = SimpleNamespace(returncode=1, stdout="", stderr=stderr)
    _stub_wpcli_environment(monkeypatch, tmp_path, proc)

    with pytest.raises(expected):
        fetch_post(_wpcli_config(tmp_path), 123)


@pytest.mark.parametrize(
    "stdout",
    [
        "not json",
        json.dumps({"ID": "not-an-int", "post_date": "2026-04-11", "post_content": "<p>ok</p>"}),
        json.dumps({"ID": 123, "post_date": "2026-04-11"}),
    ],
)
def test_fetch_post_wpcli_malformed_payloads_raise_consistently(monkeypatch, tmp_path, stdout):
    proc = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    _stub_wpcli_environment(monkeypatch, tmp_path, proc)

    with pytest.raises(MalformedResponseError):
        fetch_post(_wpcli_config(tmp_path), 123)


def test_fetch_post_rest_success_returns_structured_post_data(monkeypatch):
    payload = {
        "id": 456,
        "title": {"rendered": "Daily Log"},
        "date": "2026-04-12T09:00:00",
        "content": {"raw": "<p>08:30 Coffee</p>"},
        "status": "publish",
    }
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: _Response(200, payload))

    post = fetch_post(_rest_config(), 456)

    assert post == PostData(
        post_id=456,
        title="Daily Log",
        post_date="2026-04-12T09:00:00",
        post_content="<p>08:30 Coffee</p>",
        status="publish",
    )


@pytest.mark.parametrize(
    "status_code,expected",
    [
        (401, AuthenticationFailedError),
        (403, AuthenticationFailedError),
        (404, PostNotFoundError),
        (500, MalformedResponseError),
    ],
)
def test_fetch_post_rest_maps_http_failures(monkeypatch, status_code, expected):
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: _Response(status_code, {}))

    with pytest.raises(expected):
        fetch_post(_rest_config(), 456)


@pytest.mark.parametrize(
    "response",
    [
        _Response(200, json_error=ValueError("bad json")),
        _Response(200, []),
        _Response(200, {"id": 456, "date": "2026-04-12T09:00:00", "content": {}}),
        _Response(200, {"id": "bad", "date": "2026-04-12T09:00:00", "content": {"raw": "x"}}),
    ],
)
def test_fetch_post_rest_malformed_payloads_raise_consistently(monkeypatch, response):
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: response)

    with pytest.raises(MalformedResponseError):
        fetch_post(_rest_config(), 456)


def test_find_today_post_id_uses_configured_timezone_for_wpcli(monkeypatch):
    config = AppConfig(wordpress_mode="wpcli", wp_path="/var/www/html", wp_cli_path="wp", timezone="America/Los_Angeles")

    class _FrozenDatetime:
        @classmethod
        def now(cls, tz=None):
            import datetime as _dt

            return _dt.datetime(2026, 4, 12, 1, 30, tzinfo=_dt.timezone.utc).astimezone(tz)

    captured = {}

    def _fake_find_today_post_id_wpcli(wp_path, local_date, wp_cli_path="wp"):
        captured["wp_path"] = wp_path
        captured["local_date"] = local_date
        captured["wp_cli_path"] = wp_cli_path
        return 999

    monkeypatch.setattr("wp_log_parser.fetcher.datetime", _FrozenDatetime)
    monkeypatch.setattr("wp_log_parser.wordpress.find_today_post_id_wpcli", _fake_find_today_post_id_wpcli)

    assert find_today_post_id(config) == 999
    assert captured == {"wp_path": "/var/www/html", "local_date": "2026-04-11", "wp_cli_path": "wp"}


def test_find_today_post_id_uses_configured_timezone_for_rest(monkeypatch):
    config = AppConfig(
        wordpress_mode="rest",
        base_url="https://example.test",
        username="u",
        app_password="p",
        timezone="Asia/Tokyo",
    )

    class _FrozenDatetime:
        @classmethod
        def now(cls, tz=None):
            import datetime as _dt

            return _dt.datetime(2026, 4, 11, 15, 30, tzinfo=_dt.timezone.utc).astimezone(tz)

    captured = {}

    def _fake_find_today_post_id_rest(base_url, username, app_password, local_date, verify_ssl=True):
        captured.update(
            {
                "base_url": base_url,
                "username": username,
                "app_password": app_password,
                "local_date": local_date,
                "verify_ssl": verify_ssl,
            }
        )
        return 321

    monkeypatch.setattr("wp_log_parser.fetcher.datetime", _FrozenDatetime)
    monkeypatch.setattr("wp_log_parser.wordpress.find_today_post_id_rest", _fake_find_today_post_id_rest)

    assert find_today_post_id(config) == 321
    assert captured["local_date"] == "2026-04-12"
