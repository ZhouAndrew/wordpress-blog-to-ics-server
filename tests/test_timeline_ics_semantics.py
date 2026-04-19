from wp_log_parser.config import AppConfig
from wp_log_parser.ics import generate_ics
from wp_log_parser.models import LogEntry
from wp_log_parser.timeline import apply_timeline


def test_same_day_sequence_infers_end_time_and_ics_stays_same_day() -> None:
    entries = [
        LogEntry(date="2026-04-11", start_time="07:45", end_time=None, summary="Breakfast", raw="", status="needs_review"),
        LogEntry(date="2026-04-11", start_time="08:10", end_time=None, summary="Work", raw="", status="needs_review"),
    ]

    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=0, auto_cross_midnight=True))
    ics = generate_ics(timeline_entries, timezone="UTC")

    assert timeline_entries[0].end_time == "08:10"
    assert "DTSTART;TZID=UTC:20260411T074500" in ics
    assert "DTEND;TZID=UTC:20260411T081000" in ics


def test_explicit_range_is_preserved_in_ics() -> None:
    entries = [
        LogEntry(
            date="2026-04-11",
            start_time="18:00",
            end_time="18:23",
            summary="Dinner",
            raw="",
            status="needs_review",
        )
    ]

    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=0, auto_cross_midnight=True))
    ics = generate_ics(timeline_entries, timezone="UTC")

    assert "DTSTART;TZID=UTC:20260411T180000" in ics
    assert "DTEND;TZID=UTC:20260411T182300" in ics


def test_cross_midnight_sequence_rolls_forward_for_ics() -> None:
    entries = [
        LogEntry(date="2026-04-11", start_time="23:50", end_time=None, summary="Late work", raw="", status="needs_review"),
        LogEntry(date="2026-04-11", start_time="00:10", end_time=None, summary="Sleep", raw="", status="needs_review"),
    ]

    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=0, auto_cross_midnight=True))
    ics = generate_ics(timeline_entries, timezone="UTC")

    assert timeline_entries[0].end_time == "00:10"
    assert "DTSTART;TZID=UTC:20260411T235000" in ics
    assert "DTEND;TZID=UTC:20260412T001000" in ics
    assert "DTSTART;TZID=UTC:20260412T001000" in ics


def test_last_event_fallback_duration_rolls_across_midnight_in_ics() -> None:
    entries = [
        LogEntry(date="2026-04-11", start_time="23:50", end_time=None, summary="Late work", raw="", status="needs_review")
    ]

    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=30, auto_cross_midnight=True))
    ics = generate_ics(timeline_entries, timezone="UTC")

    assert timeline_entries[0].end_time == "00:20"
    assert "DTSTART;TZID=UTC:20260411T235000" in ics
    assert "DTEND;TZID=UTC:20260412T002000" in ics


def test_ics_never_serializes_end_before_start_for_single_event() -> None:
    entries = [
        {
            "date": "2026-04-11",
            "start_time": "23:55",
            "end_time": "00:05",
            "summary": "Cross-midnight check",
        }
    ]

    ics = generate_ics(entries, timezone="UTC")

    assert "DTSTART;TZID=UTC:20260411T235500" in ics
    assert "DTEND;TZID=UTC:20260412T000500" in ics
    assert "DTEND;TZID=UTC:20260411T000500" not in ics
