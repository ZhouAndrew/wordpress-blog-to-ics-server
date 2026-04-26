from __future__ import annotations

import json

from wp_log_parser.config import AppConfig
from wp_log_parser.debug_report import sanitize_config, write_recent_run_snapshot


def test_sanitize_config_masks_password_fields() -> None:
    config = AppConfig(app_password="wp-secret", caldav_password="caldav-secret", username="alice")

    sanitized = sanitize_config(config)

    assert sanitized["app_password"] == "***"
    assert sanitized["caldav_password"] == "***"
    assert sanitized["username"] == "alice"


def test_failed_snapshot_contains_traceback(tmp_path) -> None:
    config = AppConfig(error_dir=str(tmp_path))

    try:
        raise ValueError("boom")
    except ValueError as exc:
        last_run_path, timestamped_path = write_recent_run_snapshot(
            error_dir=config.error_dir,
            command="sync-caldav",
            success=False,
            config=config,
            error=exc,
        )

    payload = json.loads(last_run_path.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["error"]["type"] == "ValueError"
    assert "Traceback" in payload["error"]["traceback"]
    assert timestamped_path is not None
    assert timestamped_path.exists()
