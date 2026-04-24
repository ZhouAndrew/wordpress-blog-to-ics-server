from wp_log_parser.config import AppConfig
from wp_log_parser.ics import generate_ics
from wp_log_parser.models import ParsedPost
from wp_log_parser.parser import parse_post_content


def test_generate_ics_timezone_argument_does_not_shadow_datetime_timezone() -> None:
    entries = [
        {
            "date": "2026-04-11",
            "start_time": "07:45",
            "end_time": "08:00",
            "start_dt": "2026-04-11T07:45:00",
            "end_dt": "2026-04-11T08:00:00",
            "summary": "Breakfast",
        }
    ]

    ics = generate_ics(entries, timezone="Asia/Seoul")

    assert "BEGIN:VCALENDAR" in ics
    assert "DTSTAMP:" in ics
    assert "DTSTART;TZID=Asia/Seoul:20260411T074500" in ics


def test_parse_post_content_returns_parsed_post_and_handles_range_and_point() -> None:
    post_content = "\n".join(
        [
            "<!-- wp:paragraph -->",
            "<p>18:00-18:23 Dinner</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:paragraph -->",
            "<p>18:40 Cleanup</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:image -->",
            "<figure><img src=\"x.jpg\" /></figure>",
            "<!-- /wp:image -->",
            "<!-- wp:paragraph -->",
            "<p>Not a log line</p>",
            "<!-- /wp:paragraph -->",
        ]
    )

    parsed = parse_post_content(post_content, "2026-04-11", AppConfig(default_last_event_minutes=0))

    assert isinstance(parsed, ParsedPost)
    assert parsed.post_date == "2026-04-11"

    assert len(parsed.entries) == 2
    assert parsed.entries[0].start_time == "18:00"
    assert parsed.entries[0].end_time == "18:23"  # explicit range is preserved
    assert parsed.entries[0].start_dt is not None
    assert parsed.entries[0].end_dt is not None
    assert parsed.entries[0].status == "ready"
    assert parsed.entries[1].start_time == "18:40"
    assert parsed.entries[1].end_time is None
    assert parsed.entries[1].start_dt is not None
    assert parsed.entries[1].status == "needs_review"

    reasons = {item.reason for item in parsed.ignored_blocks}
    assert "unsupported_block_type" in reasons
    assert "no_leading_time" in reasons
