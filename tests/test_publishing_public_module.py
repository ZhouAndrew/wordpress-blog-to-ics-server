from datetime import datetime
from pathlib import Path

from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import PostData
from wp_log_parser.models import IgnoredBlock, LogEntry, ParsedPost
from wp_log_parser.publishing import publish_post, publish_recent


def _parsed_post() -> ParsedPost:
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
                start_dt=datetime(2026, 4, 11, 7, 45),
                end_dt=datetime(2026, 4, 11, 8, 0),
            )
        ],
        ignored_blocks=[IgnoredBlock(index=1, type="wp:image", reason="unsupported_block_type", raw="<figure />")],
    )


def test_publish_post_returns_paths_from_generated_artifacts(monkeypatch, tmp_path: Path) -> None:
    config = AppConfig(output_dir=str(tmp_path), timezone="UTC", ics_base_url="https://example.test/ics", save_ignored_blocks=True)

    monkeypatch.setattr(
        "wp_log_parser.publishing.fetch_post",
        lambda _config, _post_id: PostData(
            post_id=42,
            title="Daily Log",
            post_date="2026-04-11 09:00:00",
            post_content="<p>07:45 Breakfast</p>",
            status="publish",
        ),
    )
    monkeypatch.setattr("wp_log_parser.publishing.parse_post_content", lambda *_args, **_kwargs: _parsed_post())

    result = publish_post(config, post_id=42, verbose=False)

    assert result is not None
    assert result["post_id"] == 42
    assert result["title"] == "Daily Log"
    assert result["post_date"] == "2026-04-11 09:00:00"
    assert result["ics_file"].endswith(".ics")
    assert result["ics_url"] == f"https://example.test/ics/{result['ics_file']}"
    assert result["entry_count"] == 1
    assert result["ignored_block_count"] == 1
    assert result["warning_count"] == 0
    assert Path(result["parsed_json_file"]).exists()
    assert Path(result["ignored_file"]).exists()
    assert (tmp_path / result["ics_file"]).exists()


def test_publish_recent_delegates_to_service_mode_publish_once(monkeypatch, tmp_path: Path) -> None:
    config = AppConfig(output_dir=str(tmp_path), timezone="UTC")
    expected = {"ok": True, "published_count": 0, "items": []}
    called = {}

    def fake_publish_once(received_config: AppConfig, days: int, verbose: bool = False) -> dict:
        called["config"] = received_config
        called["days"] = days
        called["verbose"] = verbose
        return expected

    monkeypatch.setattr("wp_log_parser.publishing._publish_once", fake_publish_once)

    result = publish_recent(config, days=3, verbose=True)

    assert result is expected
    assert called == {"config": config, "days": 3, "verbose": True}
