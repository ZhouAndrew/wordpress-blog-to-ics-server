from __future__ import annotations

from typing import Any

from .models import ParsedPost


def _set_value(target: Any, key: str, value: Any) -> None:
    if isinstance(target, dict):
        target[key] = value
        return
    try:
        setattr(target, key, value)
    except (AttributeError, TypeError):
        # Some tests and compatibility paths may pass immutable placeholder
        # objects. Production parser entries are LogEntry instances and will
        # receive source metadata here.
        return


def attach_source_metadata(parsed: ParsedPost, post: Any) -> ParsedPost:
    """Attach stable WordPress source identity to a parsed post and entries."""
    post_id = post if isinstance(post, int) else post.post_id
    source_id = f"wp:{post_id}"
    _set_value(parsed, "post_id", post_id)
    _set_value(parsed, "source_id", source_id)
    for entry in getattr(parsed, "entries", []):
        _set_value(entry, "source_id", source_id)
    return parsed
