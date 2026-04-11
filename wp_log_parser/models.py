from dataclasses import dataclass
from typing import Optional


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
