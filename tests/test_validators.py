from wp_log_parser.validators import validate_python_path, validate_wp_cli


def test_validate_python_path_passes_for_python3():
    result = validate_python_path("python3")
    assert result.ok is True


def test_validate_wp_cli_fails_for_missing_binary():
    result = validate_wp_cli("definitely-not-a-real-wp-binary")
    assert result.ok is False
