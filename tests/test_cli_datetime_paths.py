from __future__ import annotations

from datetime import datetime

from wp_log_parser import cli
from wp_log_parser.config import AppConfig
from wp_log_parser.fetcher import PostData
from wp_log_parser.models import ParsedPost


def test_parse_post_uses_fetched_post_date(monkeypatch, tmp_path, capsys) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    captured: dict[str, str] = {}

    monkeypatch.setattr("wp_log_parser.cli.config_exists", lambda _path: True)
    monkeypatch.setattr("wp_log_parser.cli.load_config", lambda _path: AppConfig())
    monkeypatch.setattr("wp_log_parser.cli._print_validation", lambda _config: True)
    monkeypatch.setattr(
        "wp_log_parser.cli.fetch_post",
        lambda _config, _post_id: PostData(
            post_id=321,
            title="Log",
            post_date="2026-04-09 22:10:00",
            post_content="<p>07:45 Breakfast</p>",
            status="publish",
        ),
    )

    def fake_parse_post_content(_post_content: str, post_date: str, _config: AppConfig, verbose: bool = False) -> ParsedPost:
        captured["post_date"] = post_date
        return ParsedPost(post_date=post_date)

    monkeypatch.setattr("wp_log_parser.cli.parse_post_content", fake_parse_post_content)

    exit_code = cli.main(["parse-post", "--config", str(config_path), "--post-id", "321"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["post_date"] == "2026-04-09"
    assert '"post_date": "2026-04-09"' in output


def test_post_to_ics_passes_timeline_entries_to_writer(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    out_file = tmp_path / "x.ics"
    captured: dict[str, object] = {}

    monkeypatch.setattr("wp_log_parser.cli.config_exists", lambda _path: True)
    monkeypatch.setattr("wp_log_parser.cli.load_config", lambda _path: AppConfig(output_dir=str(tmp_path), timezone="UTC"))
    monkeypatch.setattr("wp_log_parser.cli._print_validation", lambda _config: True)
    monkeypatch.setattr(
        "wp_log_parser.cli.fetch_post",
        lambda _config, _post_id: PostData(
            post_id=111,
            title="Log",
            post_date="2026-04-11 09:00:00",
            post_content="<p>07:45 Breakfast</p>",
            status="publish",
        ),
    )

    parsed = ParsedPost(post_date="2026-04-11")
    from wp_log_parser.models import LogEntry

    parsed.entries = [
        LogEntry(
            date="2026-04-11",
            start_time="07:45",
            end_time="08:00",
            summary="Breakfast",
            raw="",
            status="ready",
            start_dt=datetime(2026, 4, 11, 7, 45),
            end_dt=datetime(2026, 4, 11, 8, 0),
        )
    ]
    monkeypatch.setattr("wp_log_parser.cli.parse_post_content", lambda *_args, **_kwargs: parsed)

    def fake_write_post_ics(_post, entries, _output_dir, _timezone):
        captured["entries"] = entries
        out_file.write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", encoding="utf-8")
        return out_file

    monkeypatch.setattr("wp_log_parser.cli.write_post_ics", fake_write_post_ics)

    exit_code = cli.main(["post-to-ics", "--config", str(config_path), "--post-id", "111"])

    assert exit_code == 0
    entries = captured["entries"]
    assert entries[0].start_dt == datetime(2026, 4, 11, 7, 45)
    assert entries[0].end_dt == datetime(2026, 4, 11, 8, 0)
