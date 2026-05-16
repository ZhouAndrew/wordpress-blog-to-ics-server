from pathlib import Path

from wp_log_parser.aliases import find_today_ics_candidates


def test_find_today_ics_candidates_sorts_same_date_by_numeric_post_id(tmp_path: Path) -> None:
    (tmp_path / "2026-05-05_post_99_diary.ics").write_text("BEGIN:VCALENDAR", encoding="utf-8")
    (tmp_path / "2026-05-05_post_100_diary.ics").write_text("BEGIN:VCALENDAR", encoding="utf-8")

    candidates = find_today_ics_candidates(tmp_path, "2026-05-05")

    assert [path.name for path in candidates] == [
        "2026-05-05_post_100_diary.ics",
        "2026-05-05_post_99_diary.ics",
    ]
