from __future__ import annotations

import json
from types import SimpleNamespace

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
        return SimpleNamespace(returncode=0, stdout=json.dumps([{"ID": 77}]), stderr="")

    monkeypatch.setattr("wp_log_parser.wordpress.subprocess.run", _fake_run)

    post_id = find_today_post_id_wpcli(str(tmp_path), "2026-04-11", "wp")

    assert post_id == 77
    assert "--date_query=after=2026-04-11 00:00:00,before=2026-04-11 23:59:59,inclusive=1" in seen["cmd"]


def test_find_today_post_id_rest_uses_local_date_range(monkeypatch):
    seen = {}

    def _fake_get(endpoint, **_kwargs):
        seen["endpoint"] = endpoint
        return _Response(200, [{"id": 88}])

    monkeypatch.setattr("requests.get", _fake_get)

    post_id = find_today_post_id_rest("https://example.test", "u", "p", "2026-04-12", True)

    assert post_id == 88
    assert "after=2026-04-12T00:00:00" in seen["endpoint"]
    assert "before=2026-04-12T23:59:59" in seen["endpoint"]
