from wp_log_parser.validators import validate_caldav_config, validate_python_path, validate_wp_cli


def test_validate_python_path_passes_for_python3():
    result = validate_python_path("python3")
    assert result.ok is True


def test_validate_wp_cli_fails_for_missing_binary():
    result = validate_wp_cli("definitely-not-a-real-wp-binary")
    assert result.ok is False


def test_validate_caldav_config_accepts_valid_values(tmp_path):
    idx_path = tmp_path / "caldav-sync-index.json"
    result = validate_caldav_config(
        "https://caldav.example.com/user/calendar",
        "alice",
        "secret",
        "example.com",
        str(idx_path),
        required=True,
    )
    assert result.ok is True


def test_validate_caldav_config_rejects_invalid_domain(tmp_path):
    idx_path = tmp_path / "caldav-sync-index.json"
    result = validate_caldav_config(
        "https://caldav.example.com/user/calendar",
        "alice",
        "secret",
        "bad domain",
        str(idx_path),
        required=True,
    )
    assert result.ok is False
