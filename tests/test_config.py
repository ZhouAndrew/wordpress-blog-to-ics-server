import json

import pytest

from wp_log_parser.config import AppConfig, create_default_config, load_config, save_config
from wp_log_parser.exceptions import ConfigError


def test_save_and_load_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = create_default_config()
    cfg.wordpress_mode = "rest"
    cfg.base_url = "https://example.com"
    save_config(cfg, str(path))

    loaded = load_config(str(path))
    assert isinstance(loaded, AppConfig)
    assert loaded.wordpress_mode == "rest"
    assert loaded.base_url == "https://example.com"


def test_load_config_rejects_non_string_caldav_fields(tmp_path):
    path = tmp_path / "config.json"
    payload = {"caldav_url": 123}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(str(path))
