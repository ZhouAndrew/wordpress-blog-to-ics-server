from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from .models import LogEntry


def normalize_time(hour: str, minute: str) -> str | None:
    h = int(hour)
    if h < 0 or h > 23:
        return None
    return f"{h:02d}:{minute}"


def apply_event_timing_rules(
    entries: List[LogEntry],
    default_last_event_minutes: int,
    auto_cross_midnight: bool,
) -> List[LogEntry]:
    for i in range(len(entries) - 1):
        current = entries[i]
        nxt = entries[i + 1]
        current_end = nxt.start_time
        if auto_cross_midnight and nxt.start_time < current.start_time:
            current_end = nxt.start_time
        current.end_time = current_end
        current.status = "ready"

    if entries:
        last = entries[-1]
        if default_last_event_minutes > 0:
            start_dt = datetime.strptime(last.start_time, "%H:%M")
            end_dt = start_dt + timedelta(minutes=default_last_event_minutes)
            last.end_time = end_dt.strftime("%H:%M")
            last.status = "ready"
        else:
            last.end_time = None
            last.status = "needs_review"
    return entries
