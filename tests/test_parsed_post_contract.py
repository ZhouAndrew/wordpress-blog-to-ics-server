from pathlib import Path

from wp_log_parser import cli
from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import PostData
from wp_log_parser.models import IgnoredBlock, LogEntry, ParsedPost
from wp_log_parser.service import run_today_pipeline
from wp_log_parser.service_mode import publish_once


def _sample_parsed_post() -> ParsedPost:
    return ParsedPost(
        post_date="2026-04-11",
        entries=[
            LogEntry(
                date="2026-04-11",
                start_time="07:45",
                end_time="08:00",
                summary="Breakfast",
                raw="<p>07:45 Breakfast</p>",
                status="ready",
            )
        ],
        ignored_blocks=[IgnoredBlock(index=3, type="wp:image", reason="unsupported_block_type", raw="<figure />")],
    )


def test_run_today_pipeline_uses_parsed_post_model(monkeypatch) -> None:
    config = AppConfig(timezone="UTC", save_ignored_blocks=True)

    monkeypatch.setattr("wp_log_parser.service.fetch_post", lambda _config, _post_id: (123, "<p>07:45 Breakfast</p>"))
    monkeypatch.setattr("wp_log_parser.service.parse_post_content", lambda *_args, **_kwargs: _sample_parsed_post())

    payload = run_today_pipeline(config)

    assert payload["post_id"] == 123
    assert payload["source_id"] == "wp:123"
    assert payload["entries"][0]["summary"] == "Breakfast"
    assert payload["ignored_blocks"][0]["reason"] == "unsupported_block_type"
    assert "BEGIN:VCALENDAR" in payload["ics_preview"]


def test_publish_once_uses_parsed_post_attributes(monkeypatch, tmp_path: Path) -> None:
    config = AppConfig(output_dir=str(tmp_path), timezone="UTC", save_ignored_blocks=True)

    monkeypatch.setattr("wp_log_parser.service_mode.list_recent_post_ids", lambda _config, _days: [42])
    monkeypatch.setattr(
        "wp_log_parser.service_mode.fetch_post",
        lambda _config, _post_id: PostData(
            post_id=42,
            title="Daily Log",
            post_date="2026-04-11 09:00:00",
            post_content="<p>07:45 Breakfast</p>",
            status="publish",
        ),
    )
    monkeypatch.setattr("wp_log_parser.service_mode.parse_post_content", lambda *_args, **_kwargs: _sample_parsed_post())

    result = publish_once(config, days=1, verbose=False)

    assert result["published_count"] == 1
    assert result["items"][0]["entry_count"] == 1
    assert result["items"][0]["ignored_block_count"] == 1
    assert Path(result["index_json"]).exists()
    assert Path(result["index_html"]).exists()


def test_export_ics_command_path_still_generates_ics(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.json"
    entries_path = tmp_path / "entries.json"
    config_path.write_text("{}", encoding="utf-8")
    entries_path.write_text(
        '[{"date":"2026-04-11","start_time":"07:45","end_time":"08:00","summary":"Breakfast"}]',
        encoding="utf-8",
    )

    monkeypatch.setattr("wp_log_parser.cli.config_exists", lambda _path: True)
    monkeypatch.setattr("wp_log_parser.cli.load_config", lambda _path: AppConfig(timezone="UTC"))
    monkeypatch.setattr("wp_log_parser.cli._print_validation", lambda _config: True)

    exit_code = cli.main(["export-ics", "--config", str(config_path), "--entries-json", str(entries_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "BEGIN:VCALENDAR" in output
