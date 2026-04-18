from __future__ import annotations

import re
from dataclasses import dataclass

from .config import AppConfig

RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):([0-5]\d)\s*(?:-|–|—|~)\s*(\d{1,2}):([0-5]\d)\b(.*)$",
    re.DOTALL,
)
POINT_RE = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\b(.*)$", re.DOTALL)


@dataclass
class ParsedLine:
    kind: str
    start_time: str
    end_time: str | None
    summary: str


@dataclass
class CustomPattern:
    name: str
    regex: str
    kind: str
    compiled: re.Pattern[str]


def _normalize_time(hour: str, minute: str) -> str | None:
    h = int(hour)
    if h < 0 or h > 23:
        return None
    return f"{h:02d}:{minute}"


def _normalize_hhmm(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    return _normalize_time(parts[0], parts[1])


def _compile_custom_pattern(name: str, regex: str, kind: str) -> CustomPattern:
    compiled = re.compile(regex, re.DOTALL)
    group_names = set(compiled.groupindex.keys())
    if "start" not in group_names:
        raise ValueError(f"custom pattern '{name}' requires named group 'start'")
    if kind == "range" and "end" not in group_names:
        raise ValueError(f"custom pattern '{name}' with kind=range requires named group 'end'")
    return CustomPattern(name=name, regex=regex, kind=kind, compiled=compiled)


def _custom_patterns(config: AppConfig) -> list[CustomPattern]:
    patterns: list[CustomPattern] = []
    raw_patterns = getattr(config, "custom_parsing_patterns", []) or []
    for i, raw in enumerate(raw_patterns, start=1):
        if isinstance(raw, str):
            name = f"custom_{i}"
            regex = raw
            kind = "point"
        else:
            item = dict(raw)
            name = str(item.get("name", f"custom_{i}"))
            regex = str(item["regex"])
            kind = str(item.get("kind", "point"))
        patterns.append(_compile_custom_pattern(name=name, regex=regex, kind=kind))
    return patterns


def parse_log_line(line: str, config: AppConfig) -> ParsedLine | None:
    # 1) custom patterns first
    for pattern in _custom_patterns(config):
        m = pattern.compiled.match(line)
        if not m:
            continue
        groups = m.groupdict()
        start = _normalize_hhmm(groups.get("start"))
        end = _normalize_hhmm(groups.get("end"))
        summary = (groups.get("summary") or "").strip()
        if not start:
            raise ValueError(f"custom pattern '{pattern.name}' produced invalid start time value")
        if pattern.kind == "range" and not end:
            raise ValueError(
                f"custom pattern '{pattern.name}' matched line but did not provide required 'end' group value"
            )
        return ParsedLine(kind=f"custom:{pattern.name}", start_time=start, end_time=end, summary=summary)

    # 2) built-in range format before point format
    range_match = RANGE_RE.match(line)
    if range_match:
        start = _normalize_time(range_match.group(1), range_match.group(2))
        end = _normalize_time(range_match.group(3), range_match.group(4))
        if not start or not end:
            return None
        summary = range_match.group(5).strip()
        return ParsedLine(kind="range", start_time=start, end_time=end, summary=summary)

    # 3) built-in point format
    point_match = POINT_RE.match(line)
    if point_match:
        start = _normalize_time(point_match.group(1), point_match.group(2))
        if not start:
            return None
        summary = point_match.group(3).strip()
        return ParsedLine(kind="point", start_time=start, end_time=None, summary=summary)

    return None
