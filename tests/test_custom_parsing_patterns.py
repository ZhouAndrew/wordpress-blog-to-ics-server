from __future__ import annotations

import json

import pytest

from wp_log_parser.config import AppConfig, load_config
from wp_log_parser.exceptions import ConfigError
from wp_log_parser.parser import parse_post_content


def _write_config(tmp_path, patterns):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"custom_parsing_patterns": patterns}), encoding="utf-8")
    return path


def test_load_config_rejects_invalid_custom_pattern_regex(tmp_path) -> None:
    path = _write_config(tmp_path, [{"name": "bad", "regex": r"^(?P<start>\d{2}:\d{2}", "type": "point"}])

    with pytest.raises(ConfigError) as excinfo:
        load_config(str(path))

    message = str(excinfo.value)
    assert "custom_parsing_patterns[1].regex is invalid" in message


def test_load_config_rejects_custom_pattern_missing_start_group(tmp_path) -> None:
    path = _write_config(tmp_path, [{"name": "no_start", "regex": r"^at (?P<summary>.*)$", "type": "point"}])

    with pytest.raises(ConfigError) as excinfo:
        load_config(str(path))

    message = str(excinfo.value)
    assert "custom_parsing_patterns[1]" in message
    assert "requires named group 'start'" in message


def test_load_config_rejects_range_custom_pattern_missing_end_group(tmp_path) -> None:
    path = _write_config(
        tmp_path,
        [{"name": "no_end", "regex": r"^from (?P<start>\d{1,2}:\d{2}) (?P<summary>.*)$", "type": "range"}],
    )

    with pytest.raises(ConfigError) as excinfo:
        load_config(str(path))

    message = str(excinfo.value)
    assert "custom_parsing_patterns[1]" in message
    assert "with kind=range requires named group 'end'" in message


def test_custom_patterns_precede_builtins_and_mix_with_builtin_patterns() -> None:
    cfg = AppConfig(
        default_last_event_minutes=0,
        custom_parsing_patterns=[
            {
                "name": "starred_builtin_shape",
                "regex": r"^(?P<start>\d{1,2}:\d{2})\s+\*\s*(?P<summary>.*)$",
                "type": "point",
            },
            {
                "name": "from_to",
                "regex": r"^from (?P<start>\d{1,2}:\d{2}) to (?P<end>\d{1,2}:\d{2}) (?P<summary>.*)$",
                "type": "range",
            },
        ],
    )
    post_content = "\n".join(
        [
            "<!-- wp:paragraph -->",
            "<p>07:45 * Custom summary wins</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:paragraph -->",
            "<p>from 08:00 to 08:30 Custom range</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:paragraph -->",
            "<p>09:00 Built-in point</p>",
            "<!-- /wp:paragraph -->",
        ]
    )

    parsed = parse_post_content(post_content, "2026-04-11", cfg)

    assert [entry.start_time for entry in parsed.entries] == ["07:45", "08:00", "09:00"]
    assert [entry.summary for entry in parsed.entries] == ["Custom summary wins", "Custom range", "Built-in point"]
    assert parsed.entries[0].end_time == "08:00"
    assert parsed.entries[1].end_time == "08:30"
    assert parsed.entries[2].end_time is None


def test_validate_config_reports_custom_pattern_error_without_parse_execution(tmp_path, capsys) -> None:
    from wp_log_parser import cli

    path = _write_config(tmp_path, [{"regex": r"^bad (?P<summary>.*)$", "type": "point"}])

    assert cli.main(["validate-config", "--config", str(path)]) == 2
    out = capsys.readouterr().out
    assert "[ERROR] config:" in out
    assert "custom_parsing_patterns[1]" in out
    assert "requires named group 'start'" in out


def test_custom_pattern_precedence_can_override_builtin_point_shape() -> None:
    cfg = AppConfig(
        default_last_event_minutes=0,
        custom_parsing_patterns=[
            {
                "name": "builtin_shape_override",
                "regex": r"^(?P<start>\d{1,2}:\d{2})\s+(?P<summary>.*)$",
                "type": "point",
            }
        ],
    )
    parsed = parse_post_content(
        "<!-- wp:paragraph --><p>7:05 Custom takes precedence</p><!-- /wp:paragraph -->",
        "2026-04-11",
        cfg,
    )

    assert parsed.entries[0].start_time == "07:05"
    assert parsed.entries[0].summary == "Custom takes precedence"
