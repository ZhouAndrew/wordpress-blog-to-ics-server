from pathlib import Path

import pytest

from wp_log_parser.aliases import find_today_ics_candidates, generate_today_ics, select_today_ics


def test_find_today_ics_candidates_sorts_same_date_by_numeric_post_id(tmp_path: Path) -> None:
    (tmp_path / "2026-05-05_post_99_diary.ics").write_text("BEGIN:VCALENDAR", encoding="utf-8")
    (tmp_path / "2026-05-05_post_100_diary.ics").write_text("BEGIN:VCALENDAR", encoding="utf-8")

    candidates = find_today_ics_candidates(tmp_path, "2026-05-05")

    assert [path.name for path in candidates] == [
        "2026-05-05_post_100_diary.ics",
        "2026-05-05_post_99_diary.ics",
    ]


def test_find_today_ics_candidates_uses_filename_tie_breaker(tmp_path: Path) -> None:
    (tmp_path / "2026-05-05_post_100_zeta.ics").write_text("BEGIN:VCALENDAR", encoding="utf-8")
    (tmp_path / "2026-05-05_post_100_alpha.ics").write_text("BEGIN:VCALENDAR", encoding="utf-8")

    candidates = find_today_ics_candidates(tmp_path, "2026-05-05")

    assert [path.name for path in candidates] == [
        "2026-05-05_post_100_alpha.ics",
        "2026-05-05_post_100_zeta.ics",
    ]


def test_select_today_ics_rejects_missing_preferred_post_id(tmp_path: Path) -> None:
    source = tmp_path / "2026-05-05_post_100_diary.ics"
    source.write_text("BEGIN:VCALENDAR", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="post ID 999"):
        select_today_ics([source], preferred_post_id=999)


def test_generate_today_ics_copy_and_symlink_are_deterministic(tmp_path: Path, monkeypatch) -> None:
    older = tmp_path / "2026-05-05_post_99_diary.ics"
    newer = tmp_path / "2026-05-05_post_100_diary.ics"
    older.write_text("OLDER", encoding="utf-8")
    newer.write_text("NEWER", encoding="utf-8")
    monkeypatch.setattr("wp_log_parser.aliases.today_date_str", lambda _tz: "2026-05-05")

    target = generate_today_ics(str(tmp_path), "UTC", mode="copy")
    assert target.read_text(encoding="utf-8") == "NEWER"

    symlink_target = generate_today_ics(str(tmp_path), "UTC", mode="symlink")
    assert symlink_target.is_symlink()
    assert symlink_target.readlink() == Path("2026-05-05_post_100_diary.ics")
