from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .exceptions import ConfigError
from .line_patterns import _compile_custom_pattern


@dataclass
class AppConfig:
    wordpress_mode: str = "wpcli"
    wp_cli_path: str = "wp"
    wp_path: str = "."
    python_path: str = "python3"
    output_dir: str = "./output"
    error_dir: str = "./errors"
    logs_dir: str = "./logs"
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
    unmatched_line_policy: str = "ignore"
    custom_parsing_patterns: list[dict[str, Any] | str] = field(default_factory=list)
    overlap_policy: str = "needs_review"
    review_entry_export_mode: str = "include"
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""
    caldav_uid_domain: str = "wordpress-blog-to-ics"
    caldav_index_path: str = "./output/caldav_sync_index.json"
    caldav_deletion_mode: str = "delete"


def _allowed_config_keys() -> set[str]:
    return {item.name for item in fields(AppConfig)}


def _require_string(data: dict[str, Any], key: str) -> None:
    if not isinstance(data.get(key), str):
        raise ConfigError(f"{key} must be a string. Update setting '{key}' in your config file.")


def _require_bool(data: dict[str, Any], key: str) -> None:
    if not isinstance(data.get(key), bool):
        raise ConfigError(f"{key} must be true or false. Update setting '{key}' in your config file.")


def _require_non_empty_string(data: dict[str, Any], key: str, *, mode: str) -> None:
    _require_string(data, key)
    if not data[key].strip():
        raise ConfigError(f"{key} is required when wordpress_mode is '{mode}'. Update setting '{key}' in your config file.")


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
        raise ConfigError(f"Config file not found: {path}. Create it with `python -m wp_log_parser init-config --config {path}`.")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Malformed JSON in config file {path}: {exc.msg} at line {exc.lineno}, column {exc.colno}.") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {path} must contain a JSON object at the top level.")

    allowed_keys = _allowed_config_keys()
    unknown_keys = sorted(set(raw) - allowed_keys)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ConfigError(f"Unknown config key(s): {joined}. Remove or rename these setting(s) in {path}.")

    defaults = create_default_config()
    data = {**asdict(defaults), **raw}

    string_fields = [
        "wordpress_mode",
        "wp_cli_path",
        "wp_path",
        "python_path",
        "output_dir",
        "error_dir",
        "logs_dir",
        "log_format",
        "base_url",
        "username",
        "app_password",
        "ics_base_url",
        "timezone",
        "overlap_policy",
        "review_entry_export_mode",
        "caldav_url",
        "caldav_username",
        "caldav_password",
        "caldav_uid_domain",
        "caldav_index_path",
        "caldav_deletion_mode",
    ]
    for field_name in string_fields:
        _require_string(data, field_name)
    for field_name in ["verify_ssl", "allow_empty_summary", "auto_cross_midnight", "save_ignored_blocks"]:
        _require_bool(data, field_name)

    if data["wordpress_mode"] not in {"wpcli", "rest"}:
        raise ConfigError("wordpress_mode must be either 'wpcli' or 'rest'. Update setting 'wordpress_mode'.")
    if data["log_format"] not in {"gutenberg_raw", "rendered_html"}:
        raise ConfigError("log_format must be 'gutenberg_raw' or 'rendered_html'. Update setting 'log_format'.")
    if data["overlap_policy"] not in {"warn", "needs_review", "error"}:
        raise ConfigError("overlap_policy must be 'warn', 'needs_review', or 'error'. Update setting 'overlap_policy'.")
    if data["review_entry_export_mode"] not in {"include", "skip", "error"}:
        raise ConfigError("review_entry_export_mode must be 'include', 'skip', or 'error'. Update setting 'review_entry_export_mode'.")

    try:
        data["default_last_event_minutes"] = int(data["default_last_event_minutes"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("default_last_event_minutes must be an integer. Update setting 'default_last_event_minutes'.") from exc

    try:
        data["post_selection_count"] = int(data.get("post_selection_count", defaults.post_selection_count))
    except (TypeError, ValueError) as exc:
        raise ConfigError("post_selection_count must be an integer. Update setting 'post_selection_count'.") from exc

    if data["caldav_deletion_mode"] not in {"delete", "cancel"}:
        raise ConfigError("caldav_deletion_mode must be 'delete' or 'cancel'. Update setting 'caldav_deletion_mode'.")

    if data["wordpress_mode"] == "wpcli":
        _require_non_empty_string(data, "wp_cli_path", mode="wpcli")
        _require_non_empty_string(data, "wp_path", mode="wpcli")
    elif data["wordpress_mode"] == "rest":
        _require_non_empty_string(data, "base_url", mode="rest")
        _require_non_empty_string(data, "username", mode="rest")
        _require_non_empty_string(data, "app_password", mode="rest")
        if not data["base_url"].startswith(("http://", "https://")):
            raise ConfigError("base_url must start with http:// or https:// when wordpress_mode is 'rest'. Update setting 'base_url'.")

    patterns = data.get("custom_parsing_patterns", [])
    if patterns is None:
        patterns = []
    if not isinstance(patterns, list):
        raise ConfigError("custom_parsing_patterns must be a list. Update setting 'custom_parsing_patterns'.")
    normalized_patterns: list[dict[str, Any] | str] = []
    for i, pattern in enumerate(patterns, start=1):
        if isinstance(pattern, str):
            try:
                _compile_custom_pattern(
                    name=f"custom_{i}",
                    regex=pattern,
                    kind="point",
                    field_path=f"custom_parsing_patterns[{i}]",
                )
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
            normalized_patterns.append(pattern)
            continue
        if not isinstance(pattern, dict):
            raise ConfigError(f"custom_parsing_patterns[{i}] must be string or object")
        if "regex" not in pattern or not isinstance(pattern["regex"], str):
            raise ConfigError(f"custom_parsing_patterns[{i}] object requires string field 'regex'")
        kind = pattern.get("kind", pattern.get("type", "point"))
        if "kind" in pattern and "type" in pattern and pattern["kind"] != pattern["type"]:
            raise ConfigError(f"custom_parsing_patterns[{i}] kind and type must match when both are set")
        if kind not in {"point", "range"}:
            raise ConfigError(f"custom_parsing_patterns[{i}] kind/type must be 'point' or 'range'")
        name = pattern.get("name") or f"custom_{i}"
        try:
            _compile_custom_pattern(
                name=str(name),
                regex=pattern["regex"],
                kind=kind,
                field_path=f"custom_parsing_patterns[{i}]",
            )
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        normalized_patterns.append({"name": str(name), "regex": pattern["regex"], "kind": kind})
    data["custom_parsing_patterns"] = normalized_patterns

    return AppConfig(**data)
