from __future__ import annotations

from wp_log_parser.config import AppConfig
from wp_log_parser.service import list_posts


def test_service_list_posts_wpcli_call_contract_unchanged(monkeypatch) -> None:
    captured = {}

    def fake_list_posts_wpcli(wp_path, wp_cli_path, per_page, limit):
        captured["args"] = (wp_path, wp_cli_path, per_page, limit)
        return []

    monkeypatch.setattr("wp_log_parser.service.list_posts_wpcli", fake_list_posts_wpcli)

    config = AppConfig(wordpress_mode="wpcli", wp_path="/var/www/html", wp_cli_path="wp", post_selection_count=55)
    result = list_posts(config)

    assert result == []
    assert captured["args"] == ("/var/www/html", "wp", 55, 55)


def test_service_list_posts_rest_call_contract_unchanged(monkeypatch) -> None:
    captured = {}

    def fake_list_posts_rest(base_url, username, app_password, verify_ssl, per_page, limit):
        captured["args"] = (base_url, username, app_password, verify_ssl, per_page, limit)
        return []

    monkeypatch.setattr("wp_log_parser.service.list_posts_rest", fake_list_posts_rest)

    config = AppConfig(
        wordpress_mode="rest",
        base_url="https://example.com",
        username="alice",
        app_password="secret",
        verify_ssl=True,
        post_selection_count=42,
    )
    result = list_posts(config)

    assert result == []
    assert captured["args"] == ("https://example.com", "alice", "secret", True, 42, 42)
