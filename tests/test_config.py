from wp_log_parser.config import AppConfig, create_default_config, load_config, save_config


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
