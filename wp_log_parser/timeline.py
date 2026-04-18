from __future__ import annotations

from datetime import datetime, timedelta

from .config import AppConfig
from .models import LogEntry, ParseWarning


def _minutes(value: str) -> int:
    dt = datetime.strptime(value, "%H:%M")
    return dt.hour * 60 + dt.minute


def _cross_day_adjust(mins: int, start_mins: int, auto_cross_midnight: bool) -> int:
    if auto_cross_midnight and mins < start_mins:
        return mins + 24 * 60
    return mins


def apply_timeline(entries: list[LogEntry], config: AppConfig) -> tuple[list[LogEntry], list[ParseWarning]]:
    warnings: list[ParseWarning] = []

    for i in range(len(entries) - 1):
        current = entries[i]
        nxt = entries[i + 1]
        current_start = _minutes(current.start_time)
        next_start = _cross_day_adjust(_minutes(nxt.start_time), current_start, config.auto_cross_midnight)

        if current.end_time is None:
            current.end_time = nxt.start_time

        current_end = _cross_day_adjust(_minutes(current.end_time), current_start, config.auto_cross_midnight)
        if current_end > next_start:
            warnings.append(
                ParseWarning(
                    index=i + 1,
                    reason="overlap",
                    message=(
                        f"event #{i + 1} end_time ({current.end_time}) exceeds next start_time ({nxt.start_time})"
                    ),
                )
            )
        current.status = "ready"

    if entries:
        last = entries[-1]
        if last.end_time is None:
            if config.default_last_event_minutes > 0:
                start_dt = datetime.strptime(last.start_time, "%H:%M")
                end_dt = start_dt + timedelta(minutes=config.default_last_event_minutes)
                last.end_time = end_dt.strftime("%H:%M")
                last.status = "ready"
            else:
                last.status = "needs_review"
        else:
            last.status = "ready"
    return entries, warnings
