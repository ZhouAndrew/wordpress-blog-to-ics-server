from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ValidationResult:
    ok: bool
    name: str
    message: str
    details: Optional[str] = None


@dataclass
class LogEntry:
    date: str
    start_time: str
    end_time: Optional[str]
    summary: str
    raw: str
    status: str
    source_id: Optional[str] = None
    start_dt: datetime | None = None
    end_dt: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_dt": self.start_dt.isoformat() if self.start_dt else None,
            "end_dt": self.end_dt.isoformat() if self.end_dt else None,
            "summary": self.summary,
            "raw": self.raw,
            "status": self.status,
            "source_id": self.source_id,
        }


@dataclass
class ParseWarning:
    index: int
    reason: str
    message: str


@dataclass
class IgnoredBlock:
    index: int
    type: str
    reason: str
    raw: str = ""


@dataclass
class ParsedPost:
    post_date: str
    entries: list[LogEntry] = field(default_factory=list)
    ignored_blocks: list[IgnoredBlock] = field(default_factory=list)
    post_id: Optional[int] = None
    source_id: Optional[str] = None
    managed_by: str = "wp_log_parser"
    warnings: list[ParseWarning] = field(default_factory=list)

    def to_dict(self, include_ignored: bool = True) -> dict[str, Any]:
        return {
            "post_date": self.post_date,
            "post_id": self.post_id,
            "source_id": self.source_id,
            "managed_by": self.managed_by,
            "entries": [entry.to_dict() for entry in self.entries],
            "ignored_blocks": [block.__dict__ for block in self.ignored_blocks] if include_ignored else [],
            "warnings": [item.__dict__ for item in self.warnings],
        }
