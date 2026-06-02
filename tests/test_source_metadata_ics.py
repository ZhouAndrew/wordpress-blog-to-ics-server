from pathlib import Path

from wp_log_parser import cli
from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import PostData
from wp_log_parser.ics import generate_ics
from wp_log_parser.parser import parse_post_content
from wp_log_parser.source_metadata import attach_source_metadata


def _uids(ics: str) -> list[str]:
    return [line.removeprefix("UID:") for line in ics.splitlines() if line.startswith("UID:")]


def _post(post_id: int, output_date: str = "2026-04-11 09:00:00") -> PostData:
    return PostData(
        post_id=post_id,
        title=f"Daily {post_id}",
        post_date=output_date,
        post_content=(
            "<!-- wp:paragraph -->\n"
            "<p>07:45 Breakfast</p>\n"
            "<!-- /wp:paragraph -->"
        ),
        status="publish",
    )


def test_identical_events_from_different_posts_generate_different_uids() -> None:
    config = AppConfig(timezone="UTC")
    parsed_one = parse_post_content(_post(101).post_content, "2026-04-11", config)
    parsed_two = parse_post_content(_post(202).post_content, "2026-04-11", config)
    attach_source_metadata(parsed_one, _post(101))
    attach_source_metadata(parsed_two, _post(202))

    uid_one = _uids(generate_ics(parsed_one.entries, timezone="UTC"))[0]
    uid_two = _uids(generate_ics(parsed_two.entries, timezone="UTC"))[0]

    assert uid_one != uid_two


def test_post_to_ics_command_writes_source_property(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    config = AppConfig(output_dir=str(tmp_path), timezone="UTC")

    monkeypatch.setattr("wp_log_parser.cli.config_exists", lambda _path: True)
    monkeypatch.setattr("wp_log_parser.cli.load_config", lambda _path: config)
    monkeypatch.setattr("wp_log_parser.cli._print_validation", lambda _config, **_kwargs: True)
    monkeypatch.setattr("wp_log_parser.service.fetch_post", lambda _config, _post_id: _post(303))

    exit_code = cli.main(["post-to-ics", "--config", str(config_path), "--post-id", "303"])

    assert exit_code == 0
    ics_files = list(tmp_path.glob("*.ics"))
    assert len(ics_files) == 1
    assert "X-WP-LOG-PARSER-SOURCE:wp:303" in ics_files[0].read_text(encoding="utf-8")


def test_publish_ics_command_writes_source_property(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    config = AppConfig(output_dir=str(tmp_path), timezone="UTC")

    monkeypatch.setattr("wp_log_parser.cli.config_exists", lambda _path: True)
    monkeypatch.setattr("wp_log_parser.cli.load_config", lambda _path: config)
    monkeypatch.setattr("wp_log_parser.cli._print_validation", lambda _config, **_kwargs: True)
    monkeypatch.setattr("wp_log_parser.service_mode.list_recent_post_ids", lambda _config, _days: [404])
    monkeypatch.setattr("wp_log_parser.service_mode.fetch_post", lambda _config, _post_id: _post(404))

    exit_code = cli.main(["publish-ics", "--config", str(config_path), "--days", "1"])

    assert exit_code == 0
    ics_files = [path for path in tmp_path.glob("*.ics") if path.name != "today.ics"]
    assert len(ics_files) == 1
    assert "X-WP-LOG-PARSER-SOURCE:wp:404" in ics_files[0].read_text(encoding="utf-8")
