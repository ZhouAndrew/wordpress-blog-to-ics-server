from datetime import datetime

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
    assert timeline_entries[0].start_dt == datetime(2026, 4, 11, 7, 45)
    assert timeline_entries[0].end_dt == datetime(2026, 4, 11, 8, 10)
    assert "DTSTART:20260411T074500Z" in ics
    assert "DTEND:20260411T081000Z" in ics


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

    assert timeline_entries[0].start_dt == datetime(2026, 4, 11, 18, 0)
    assert timeline_entries[0].end_dt == datetime(2026, 4, 11, 18, 23)
    assert "DTSTART:20260411T180000Z" in ics
    assert "DTEND:20260411T182300Z" in ics


def test_cross_midnight_sequence_rolls_forward_for_ics() -> None:
    entries = [
        LogEntry(date="2026-04-11", start_time="23:50", end_time=None, summary="Late work", raw="", status="needs_review"),
        LogEntry(date="2026-04-11", start_time="00:10", end_time=None, summary="Sleep", raw="", status="needs_review"),
    ]

    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=0, auto_cross_midnight=True))
    ics = generate_ics(timeline_entries, timezone="UTC")

    assert timeline_entries[0].end_time == "00:10"
    assert timeline_entries[0].start_dt == datetime(2026, 4, 11, 23, 50)
    assert timeline_entries[0].end_dt == datetime(2026, 4, 12, 0, 10)
    assert timeline_entries[1].start_dt == datetime(2026, 4, 12, 0, 10)
    assert "DTSTART:20260411T235000Z" in ics
    assert "DTEND:20260412T001000Z" in ics
    assert "DTSTART:20260412T001000Z" in ics


def test_last_event_fallback_duration_rolls_across_midnight_in_ics() -> None:
    entries = [
        LogEntry(date="2026-04-11", start_time="23:50", end_time=None, summary="Late work", raw="", status="needs_review")
    ]

    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=30, auto_cross_midnight=True))
    ics = generate_ics(timeline_entries, timezone="UTC")

    assert timeline_entries[0].end_time == "00:20"
    assert timeline_entries[0].end_dt == datetime(2026, 4, 12, 0, 20)
    assert "DTSTART:20260411T235000Z" in ics
    assert "DTEND:20260412T002000Z" in ics


def test_end_datetime_is_always_on_or_after_start_datetime() -> None:
    entries = [
        LogEntry(date="2026-04-11", start_time="23:55", end_time="00:05", summary="Cross-midnight check", raw="", status="needs_review")
    ]
    timeline_entries, _warnings = apply_timeline(entries, AppConfig(default_last_event_minutes=0, auto_cross_midnight=True))

    assert timeline_entries[0].start_dt == datetime(2026, 4, 11, 23, 55)
    assert timeline_entries[0].end_dt == datetime(2026, 4, 12, 0, 5)
    assert timeline_entries[0].end_dt >= timeline_entries[0].start_dt


def test_ics_uses_datetime_fields_exactly() -> None:
    entries = [
        {
            "date": "2026-04-11",
            "start_time": "23:55",
            "end_time": "00:05",
            "start_dt": "2026-04-13T05:30:00",
            "end_dt": "2026-04-13T05:45:00",
            "summary": "Cross-midnight check",
        }
    ]

    ics = generate_ics(entries, timezone="UTC")

    assert "DTSTART:20260413T053000Z" in ics
    assert "DTEND:20260413T054500Z" in ics
    assert "DTSTART:20260411T235500Z" not in ics


def test_ics_timezone_contract_is_utc_only_without_vtimezone_or_tzid() -> None:
    entries = [
        {
            "date": "2026-04-11",
            "start_time": "07:45",
            "end_time": "08:10",
            "start_dt": "2026-04-11T07:45:00",
            "end_dt": "2026-04-11T08:10:00",
            "summary": "Breakfast",
        },
        {
            "date": "2026-04-11",
            "start_time": "08:10",
            "end_time": None,
            "start_dt": "2026-04-11T08:10:00",
            "end_dt": None,
            "summary": "Work",
        },
    ]

    ics = generate_ics(entries, timezone="Asia/Seoul")

    assert "BEGIN:VTIMEZONE" not in ics
    assert "TZID" not in ics
    assert "DTSTART:20260411T074500Z" in ics
    assert "DTEND:20260411T081000Z" in ics
    assert "DTSTART:20260411T081000Z" in ics
    date_lines = [line for line in ics.splitlines() if line.startswith(("DTSTART", "DTEND"))]
    assert date_lines == [
        "DTSTART:20260411T074500Z",
        "DTEND:20260411T081000Z",
        "DTSTART:20260411T081000Z",
    ]


def test_ics_timezone_contract_converts_aware_datetimes_to_utc_z() -> None:
    entries = [
        {
            "date": "2026-04-11",
            "start_time": "07:45",
            "end_time": "08:10",
            "start_dt": "2026-04-11T07:45:00+09:00",
            "end_dt": "2026-04-11T08:10:00+09:00",
            "summary": "Breakfast",
        }
    ]

    ics = generate_ics(entries, timezone="Asia/Seoul")

    assert "DTSTART:20260410T224500Z" in ics
    assert "DTEND:20260410T231000Z" in ics
    assert "TZID" not in ics
