from wp_log_parser.ics import generate_ics, generate_single_event_ics


def _assert_fold_limit(ics_payload: str, limit: int = 75) -> None:
    for line in ics_payload.split("\r\n"):
        if not line:
            continue
        assert len(line.encode("utf-8")) <= limit


def _summary_value(ics_payload: str) -> str:
    lines = ics_payload.split("\r\n")
    for idx, line in enumerate(lines):
        if line.startswith("SUMMARY:"):
            parts = [line]
            j = idx + 1
            while j < len(lines) and lines[j].startswith(" "):
                parts.append(lines[j][1:])
                j += 1
            return "".join(parts)
    raise AssertionError("missing SUMMARY")


def test_local_ics_summary_escaping_and_line_folding() -> None:
    long_text = "A" * 120
    summary = f"a,b;c\\d\nline\r\nnext\rsolo {long_text}"
    entries = [
        {
            "date": "2026-04-11",
            "start_time": "07:45",
            "end_time": None,
            "start_dt": "2026-04-11T07:45:00",
            "end_dt": None,
            "summary": summary,
        }
    ]

    ics = generate_ics(entries, timezone="UTC")

    _assert_fold_limit(ics)
    summary_line = _summary_value(ics)
    assert "SUMMARY:a\\,b\\;c\\\\d\\nline\\nnext\\nsolo" in summary_line


def test_single_event_ics_utf8_folding_for_non_ascii_summary() -> None:
    long_non_ascii = "한글" * 50
    payload = generate_single_event_ics(
        uid="id@example.com",
        summary=f"메모,세미콜론;백슬래시\\ 줄바꿈\n{long_non_ascii}",
        start_dt=__import__("datetime").datetime(2026, 4, 11, 7, 45),
        timezone="UTC",
    )

    _assert_fold_limit(payload)
    summary_line = _summary_value(payload)
    assert "SUMMARY:메모\\,세미콜론\\;백슬래시\\\\ 줄바꿈\\n" in summary_line
