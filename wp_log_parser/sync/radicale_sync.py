from __future__ import annotations

from typing import Protocol

from ..models import ParsedPost


class SyncAdapter(Protocol):
    def push(self, parsed_post: ParsedPost) -> None:  # pragma: no cover - extension point
        ...


class RadicaleSyncAdapter:
    """
    Placeholder for future Radicale synchronization integration.
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password

    def push(self, parsed_post: ParsedPost) -> None:  # pragma: no cover - extension point
        raise NotImplementedError("Radicale sync is not implemented yet.")
