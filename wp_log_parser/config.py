from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ConfigError


@dataclass
class AppConfig:
    wordpress_mode: str = "wpcli"
    wp_cli_path: str = "wp"
    wp_path: str = "."
    python_path: str = "python3"
    output_dir: str = "./output"
    error_dir: str = "./errors"
    log_format: str = "gutenberg_raw"
    base_url: str = ""
    username: str = ""
    app_password: str = ""
    verify_ssl: bool = True
    ics_base_url: str = ""
    timezone: str = "UTC"
    default_last_event_minutes: int = 30
    post_selection_count: int = 20
    allow_empty_summary: bool = False
    auto_cross_midnight: bool = True
    save_ignored_blocks: bool = True
    custom_parsing_patterns: list[dict[str, Any] | str] = field(default_factory=list)
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""
    caldav_uid_domain: str = "wordpress-blog-to-ics"
    caldav_index_path: str = "./output/caldav_sync_index.json"
    caldav_deletion_mode: str = "delete"


def create_default_config() -> AppConfig:
    return AppConfig()


def config_exists(path: str) -> bool:
    return Path(path).exists()


def save_config(config: AppConfig, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_config(path: str) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file: {path}") from exc

    defaults = create_default_config()
    data = {**asdict(defaults), **raw}

    if data["wordpress_mode"] not in {"wpcli", "rest"}:
        raise ConfigError("wordpress_mode must be either 'wpcli' or 'rest'")
    if data["log_format"] not in {"gutenberg_raw", "rendered_html"}:
        raise ConfigError("log_format must be 'gutenberg_raw' or 'rendered_html'")

    try:
        data["default_last_event_minutes"] = int(data["default_last_event_minutes"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("default_last_event_minutes must be an integer") from exc

    try:
        data["post_selection_count"] = int(data.get("post_selection_count", defaults.post_selection_count))
    except (TypeError, ValueError) as exc:
        raise ConfigError("post_selection_count must be an integer") from exc

    for field_name in [
        "caldav_url",
        "caldav_username",
        "caldav_password",
        "caldav_uid_domain",
        "caldav_index_path",
        "caldav_deletion_mode",
    ]:
        value = data.get(field_name, "")
        if not isinstance(value, str):
            raise ConfigError(f"{field_name} must be a string")
    if data["caldav_deletion_mode"] not in {"delete", "cancel"}:
        raise ConfigError("caldav_deletion_mode must be 'delete' or 'cancel'")

    patterns = data.get("custom_parsing_patterns", [])
    if patterns is None:
        patterns = []
    if not isinstance(patterns, list):
        raise ConfigError("custom_parsing_patterns must be a list")
    normalized_patterns: list[dict[str, Any] | str] = []
    for i, pattern in enumerate(patterns, start=1):
        if isinstance(pattern, str):
            normalized_patterns.append(pattern)
            continue
        if not isinstance(pattern, dict):
            raise ConfigError(f"custom_parsing_patterns[{i}] must be string or object")
        if "regex" not in pattern or not isinstance(pattern["regex"], str):
            raise ConfigError(f"custom_parsing_patterns[{i}] object requires string field 'regex'")
        kind = pattern.get("kind", "point")
        if kind not in {"point", "range"}:
            raise ConfigError(f"custom_parsing_patterns[{i}] kind must be 'point' or 'range'")
        name = pattern.get("name") or f"custom_{i}"
        normalized_patterns.append({"name": str(name), "regex": pattern["regex"], "kind": kind})
    data["custom_parsing_patterns"] = normalized_patterns

    return AppConfig(**data)
