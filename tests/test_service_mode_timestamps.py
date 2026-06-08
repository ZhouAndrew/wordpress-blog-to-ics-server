from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from wp_log_parser import service_mode
from wp_log_parser.config import AppConfig


class FixedDateTime(datetime):
    calls: list[object] = []

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        cls.calls.append(tz)
        if tz is None:
            raise AssertionError("service logs must request a timezone-aware timestamp")
        return cls(2026, 6, 8, 12, 34, 56, tzinfo=timezone.utc).astimezone(tz)


def test_quiet_http_handler_logs_timezone_aware_utc_timestamp(monkeypatch, capsys) -> None:
    monkeypatch.setattr(service_mode, "datetime", FixedDateTime)
    FixedDateTime.calls = []

    request = SimpleNamespace(address_string=lambda: "127.0.0.1")
    service_mode.QuietHTTPRequestHandler.log_message(request, "GET %s", "/today.ics")

    output = capsys.readouterr().out
    assert "[2026-06-08T12:34:56+00:00] [HTTP] 127.0.0.1 - GET /today.ics" in output
    assert FixedDateTime.calls == [timezone.utc]


def test_run_service_loop_logs_publish_cycle_in_configured_timezone(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(service_mode, "datetime", FixedDateTime)
    monkeypatch.setattr(service_mode.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(service_mode.time, "sleep", lambda _seconds: None)
    FixedDateTime.calls = []

    class FakeServer:
        def __init__(self) -> None:
            self.shutdown_called = False
            self.close_called = False

        def shutdown(self) -> None:
            self.shutdown_called = True

        def server_close(self) -> None:
            self.close_called = True

    fake_server = FakeServer()
    monkeypatch.setattr(service_mode, "start_http_server", lambda *_args, **_kwargs: fake_server)

    publish_calls = {"count": 0}

    def fake_publish_once(*_args, **_kwargs):
        publish_calls["count"] += 1
        if publish_calls["count"] == 2:
            raise KeyboardInterrupt()
        return {}

    monkeypatch.setattr(service_mode, "publish_once", fake_publish_once)

    config = AppConfig(output_dir=str(tmp_path), timezone="Asia/Tokyo")
    with pytest.raises(KeyboardInterrupt):
        service_mode.run_service_loop(config, days=1, interval_seconds=60, host="127.0.0.1", port=8000)

    output = capsys.readouterr().out
    assert "[INFO] Publish cycle started at 2026-06-08T21:34:56+09:00" in output
    assert str(FixedDateTime.calls[-1]) == "Asia/Tokyo"
    assert fake_server.shutdown_called is True
    assert fake_server.close_called is True
