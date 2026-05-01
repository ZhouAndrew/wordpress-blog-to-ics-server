from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import AppConfig, load_config, save_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(token in lowered for token in ("password", "token", "secret", "auth", "apikey", "api_key")):
        return "***" if value else ""
    return value


def write_runtime_log(config: AppConfig, phase: str, message: str, details: dict[str, Any] | None = None) -> Path:
    log_dir = Path(config.logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = log_dir / f"runtime-{day}.log"
    payload = {"ts": _utc_now(), "phase": phase, "message": message}
    if details:
        payload["details"] = {k: _redact_value(k, v) for k, v in details.items()}
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def config_get(path: str, key: str) -> Any:
    cfg = load_config(path)
    data = cfg.__dict__
    if key not in data:
        raise KeyError(f"Unknown config key: {key}")
    return _redact_value(key, data[key])


def config_set(path: str, key: str, value: str) -> None:
    cfg = load_config(path)
    if key not in cfg.__dict__:
        raise KeyError(f"Unknown config key: {key}")
    if key == "custom_parsing_patterns":
        raise ValueError("custom_parsing_patterns is not supported by plain string set")
    current = cfg.__dict__[key]
    if isinstance(current, bool):
        normalized = value.strip().lower()
        if normalized not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError(f"Invalid bool value for {key}: {value}")
        parsed = normalized in {"true", "1", "yes"}
    elif isinstance(current, int):
        parsed = int(value)
    else:
        parsed = value

    if key == "wordpress_mode" and parsed not in {"wpcli", "rest"}:
        raise ValueError("wordpress_mode must be one of: wpcli, rest")
    if key == "log_format" and parsed not in {"gutenberg_raw", "rendered_html"}:
        raise ValueError("log_format must be one of: gutenberg_raw, rendered_html")
    if key == "caldav_deletion_mode" and parsed not in {"delete", "cancel"}:
        raise ValueError("caldav_deletion_mode must be one of: delete, cancel")
    if key == "timezone":
        ZoneInfo(str(parsed))
    if key == "default_last_event_minutes" and int(parsed) < 0:
        raise ValueError("default_last_event_minutes must be >= 0")
    if key == "post_selection_count" and not (1 <= int(parsed) <= 200):
        raise ValueError("post_selection_count must be between 1 and 200")

    setattr(cfg, key, parsed)
    save_config(cfg, path)


def edit_config_file(path: str) -> None:
    editor = os.environ.get("EDITOR")
    if editor:
        subprocess.run([editor, path], check=False)
    elif os.name == "nt":
        subprocess.run(["notepad", path], check=False)
    else:
        subprocess.run(["vi", path], check=False)
