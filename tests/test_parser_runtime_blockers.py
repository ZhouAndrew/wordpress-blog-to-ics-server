from wp_log_parser import parse_post_content as public_parse_post_content
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
    assert "DTSTART:20260410T224500Z" in ics


def test_public_parse_post_content_defaults_to_app_config_when_config_is_omitted() -> None:
    post_content = "\n".join(
        [
            "<!-- wp:paragraph -->",
            "<p>07:45 Breakfast</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:paragraph -->",
            "<p>Not a log line</p>",
            "<!-- /wp:paragraph -->",
        ]
    )

    parsed = public_parse_post_content(post_content, "2026-04-11")

    assert isinstance(parsed, ParsedPost)
    assert parsed.entries[0].start_time == "07:45"
    assert parsed.entries[0].end_time == "08:15"  # AppConfig default fallback duration is applied.
    assert parsed.entries[0].status == "ready"
    assert [block.reason for block in parsed.ignored_blocks] == ["no_leading_time"]


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


def test_parse_post_content_rendered_html_paragraphs() -> None:
    post_content = "\n".join(
        [
            "<div><p>07:45 Breakfast</p></div>",
            "<p>Not a log line</p>",
            "<p>08:30 Enabled Thunderbird on laptop</p>",
        ]
    )
    config = AppConfig(log_format="rendered_html", default_last_event_minutes=0)

    parsed = parse_post_content(post_content, "2026-04-11", config)

    assert [entry.start_time for entry in parsed.entries] == ["07:45", "08:30"]
    assert [entry.summary for entry in parsed.entries] == ["Breakfast", "Enabled Thunderbird on laptop"]
    assert parsed.entries[0].end_time == "08:30"
    assert parsed.entries[1].end_time is None
    assert {item.reason for item in parsed.ignored_blocks} == {"no_leading_time"}


def test_parse_post_content_gutenberg_raw_unchanged() -> None:
    post_content = "\n".join(
        [
            "<!-- wp:paragraph -->",
            "<p>07:45 Breakfast</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:image -->",
            "<figure><img src=\"x.jpg\" /></figure>",
            "<!-- /wp:image -->",
            "<!-- wp:paragraph -->",
            "<p>08:30 Work</p>",
            "<!-- /wp:paragraph -->",
        ]
    )
    config = AppConfig(log_format="gutenberg_raw", default_last_event_minutes=0)

    parsed = parse_post_content(post_content, "2026-04-11", config)

    assert [entry.start_time for entry in parsed.entries] == ["07:45", "08:30"]
    assert parsed.entries[0].end_time == "08:30"
    assert parsed.entries[1].end_time is None
    assert {item.reason for item in parsed.ignored_blocks} == {"unsupported_block_type"}


def test_range_builtin_syntax_variants_are_matched_before_point_pattern() -> None:
    separators = ["-", " - ", "–", "—", "~"]
    for separator in separators:
        parsed = parse_post_content(
            f"<!-- wp:paragraph --><p>18:00{separator}18:23 Dinner</p><!-- /wp:paragraph -->",
            "2026-04-11",
            AppConfig(default_last_event_minutes=0),
        )

        assert len(parsed.entries) == 1
        assert parsed.entries[0].start_time == "18:00"
        assert parsed.entries[0].end_time == "18:23"
        assert parsed.entries[0].summary == "Dinner"
        assert parsed.entries[0].status == "ready"


def test_unmatched_line_can_append_to_previous_entry() -> None:
    post_content = "\n".join(
        [
            "<!-- wp:paragraph -->",
            "<p>07:45 Breakfast</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:paragraph -->",
            "<p>with extra notes</p>",
            "<!-- /wp:paragraph -->",
            "<!-- wp:paragraph -->",
            "<p>08:00 Work</p>",
            "<!-- /wp:paragraph -->",
        ]
    )

    parsed = parse_post_content(
        post_content,
        "2026-04-11",
        AppConfig(default_last_event_minutes=0, unmatched_line_policy="append_to_previous"),
    )

    assert [entry.summary for entry in parsed.entries] == ["Breakfast with extra notes", "Work"]
    assert [block.reason for block in parsed.ignored_blocks] == []


def test_unsupported_gutenberg_blocks_report_index_type_reason_and_raw() -> None:
    post_content = "\n".join(
        [
            "<!-- wp:file -->",
            "<div class=\"wp-block-file\"><a href=\"x.pdf\">PDF</a></div>",
            "<!-- /wp:file -->",
            "<!-- wp:image -->",
            "<figure><img src=\"x.jpg\" /></figure>",
            "<!-- /wp:image -->",
            "<!-- wp:list -->",
            "<ul><li>Item</li></ul>",
            "<!-- /wp:list -->",
            "<!-- wp:heading -->",
            "<h2>Heading</h2>",
            "<!-- /wp:heading -->",
        ]
    )

    parsed = parse_post_content(post_content, "2026-04-11", AppConfig(default_last_event_minutes=0))

    ignored = [block.to_dict() for block in parsed.ignored_blocks]
    assert [item["index"] for item in ignored] == [1, 2, 3, 4]
    assert [item["type"] for item in ignored] == ["wp:file", "wp:image", "wp:list", "wp:heading"]
    assert {item["reason"] for item in ignored} == {"unsupported_block_type"}
    assert all(item["raw"] for item in ignored)
