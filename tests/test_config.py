import json
import pytest

from wp_log_parser.config import AppConfig, create_default_config, load_config, save_config
from wp_log_parser.exceptions import ConfigError


def test_save_and_load_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = create_default_config()
    cfg.wordpress_mode = "rest"
    cfg.base_url = "https://example.com"
    cfg.username = "alice"
    cfg.app_password = "secret"
    save_config(cfg, str(path))

    loaded = load_config(str(path))
    assert isinstance(loaded, AppConfig)
    assert loaded.wordpress_mode == "rest"
    assert loaded.base_url == "https://example.com"


def test_load_config_rejects_missing_file(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(str(path))


def test_load_config_rejects_malformed_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"wordpress_mode": ', encoding="utf-8")

    with pytest.raises(ConfigError, match="Malformed JSON"):
        load_config(str(path))


def test_load_config_rejects_unknown_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"wordpress_mode": "wpcli", "surprise": True}), encoding="utf-8")

    with pytest.raises(ConfigError, match="Unknown config key"):
        load_config(str(path))


def test_load_config_rejects_invalid_wordpress_mode(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"wordpress_mode": "ftp"}), encoding="utf-8")

    with pytest.raises(ConfigError, match="wordpress_mode"):
        load_config(str(path))


def test_load_config_wpcli_does_not_require_rest_credentials(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"wordpress_mode": "wpcli", "wp_cli_path": "wp", "wp_path": "."}), encoding="utf-8")

    loaded = load_config(str(path))

    assert loaded.wordpress_mode == "wpcli"
    assert loaded.username == ""
    assert loaded.app_password == ""


@pytest.mark.parametrize("missing_key", ["base_url", "username", "app_password"])
def test_load_config_rest_requires_mode_specific_values(tmp_path, missing_key):
    path = tmp_path / "config.json"
    payload = {
        "wordpress_mode": "rest",
        "base_url": "https://example.com",
        "username": "alice",
        "app_password": "secret",
    }
    payload[missing_key] = ""
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigError, match=missing_key):
        load_config(str(path))


def test_load_config_rejects_non_string_caldav_fields(tmp_path):
    path = tmp_path / "config.json"
    payload = {"caldav_url": 123}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(str(path))


def test_load_config_rejects_invalid_caldav_deletion_mode(tmp_path):
    path = tmp_path / "config.json"
    payload = {"caldav_deletion_mode": "hard-delete"}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(str(path))
