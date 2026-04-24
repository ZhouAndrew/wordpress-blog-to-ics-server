from __future__ import annotations

from datetime import datetime, timedelta

from .config import AppConfig
from .models import LogEntry, ParseWarning


def _entry_start_datetime(entry: LogEntry, baseline: datetime | None, auto_cross_midnight: bool) -> datetime:
    candidate = datetime.strptime(f"{entry.date} {entry.start_time}", "%Y-%m-%d %H:%M")
    if baseline is not None and auto_cross_midnight:
        while candidate < baseline:
            candidate += timedelta(days=1)
    return candidate


def _entry_end_datetime(entry: LogEntry, start_dt: datetime) -> datetime | None:
    if entry.end_time is None:
        return None
    candidate = datetime.strptime(f"{entry.date} {entry.end_time}", "%Y-%m-%d %H:%M")
    while candidate < start_dt:
        candidate += timedelta(days=1)
    return candidate


def apply_timeline(entries: list[LogEntry], config: AppConfig) -> tuple[list[LogEntry], list[ParseWarning]]:
    warnings: list[ParseWarning] = []
    previous_start: datetime | None = None

    for i, entry in enumerate(entries):
        entry.start_dt = _entry_start_datetime(entry, previous_start, config.auto_cross_midnight)
        entry.end_dt = _entry_end_datetime(entry, entry.start_dt)
        previous_start = entry.start_dt

    for i in range(len(entries) - 1):
        current = entries[i]
        nxt = entries[i + 1]

        if current.end_time is None:
            current.end_time = nxt.start_dt.strftime("%H:%M")
            current.end_dt = nxt.start_dt

        if current.end_dt is None:
            current.end_dt = _entry_end_datetime(current, current.start_dt)

        if current.end_dt and current.end_dt > nxt.start_dt:
            warnings.append(
                ParseWarning(
                    index=i + 1,
                    reason="overlap",
                    message=(
                        f"event #{i + 1} end_time ({current.end_time}) exceeds next start_time ({nxt.start_time})"
                    ),
                )
            )

        if current.end_dt and current.end_dt < current.start_dt:
            warnings.append(
                ParseWarning(
                    index=i + 1,
                    reason="invalid_end_before_start",
                    message=f"event #{i + 1} end datetime is before start datetime; end adjusted",
                )
            )
            current.end_dt = current.start_dt
            current.end_time = current.end_dt.strftime("%H:%M")
        current.status = "ready"

    if entries:
        last = entries[-1]
        if last.end_time is None:
            if config.default_last_event_minutes > 0:
                last.end_dt = last.start_dt + timedelta(minutes=config.default_last_event_minutes)
                last.end_time = last.end_dt.strftime("%H:%M")
                last.status = "ready"
            else:
                last.end_dt = None
                last.status = "needs_review"
        else:
            if last.end_dt is None:
                last.end_dt = _entry_end_datetime(last, last.start_dt)
            last.status = "ready"

        if last.end_dt is not None and last.end_dt < last.start_dt:
            warnings.append(
                ParseWarning(
                    index=len(entries),
                    reason="invalid_end_before_start",
                    message=f"event #{len(entries)} end datetime is before start datetime; end adjusted",
                )
            )
            last.end_dt = last.start_dt
            last.end_time = last.end_dt.strftime("%H:%M")
    return entries, warnings
