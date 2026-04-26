from __future__ import annotations

import json
import traceback
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig

_SECRET_MARK = "***"
_SECRET_HINTS = (
    "password",
    "token",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "auth",
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def _sanitize_secret_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return _SECRET_MARK if value else ""
    return _SECRET_MARK


def _sanitize_mapping(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if _is_secret_key(key):
            sanitized[key] = _sanitize_secret_value(value)
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_mapping(value)
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_mapping(item) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[key] = value
    return sanitized


def sanitize_config(config: AppConfig) -> dict[str, Any]:
    return _sanitize_mapping(asdict(config))


def sanitize_payload(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return _sanitize_mapping(payload)
    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    if is_dataclass(payload):
        return _sanitize_mapping(asdict(payload))
    return payload


def write_recent_run_snapshot(
    *,
    error_dir: str,
    command: str,
    success: bool,
    config: AppConfig,
    dry_run: bool | None = None,
    summary: dict[str, Any] | None = None,
    processed_post_ids: list[int] | None = None,
    changed_post_count: int | None = None,
    caldav_counts: dict[str, int] | None = None,
    index_path: str | None = None,
    debug_operations: list[dict[str, Any]] | None = None,
    error: BaseException | None = None,
) -> tuple[Path, Path | None]:
    target_dir = Path(error_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "timestamp_utc": _utc_timestamp(),
        "command": command,
        "success": success,
        "dry_run": dry_run,
        "config": sanitize_config(config),
        "summary": sanitize_payload(summary) if summary is not None else None,
        "processed_post_ids": processed_post_ids or [],
        "changed_post_count": changed_post_count,
        "caldav_counts": caldav_counts or {},
        "index_path": index_path,
    }
    if debug_operations:
        payload["debug_operations"] = sanitize_payload(debug_operations)

    if error is not None:
        payload["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        }

    last_run_path = target_dir / "last_run.json"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    last_run_path.write_text(serialized, encoding="utf-8")

    timestamped_path: Path | None = None
    if not success:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        timestamped_path = target_dir / f"debug_{ts}.json"
        timestamped_path.write_text(serialized, encoding="utf-8")

    return last_run_path, timestamped_path
