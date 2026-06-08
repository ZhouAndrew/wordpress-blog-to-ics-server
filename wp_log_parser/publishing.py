from __future__ import annotations

"""Deprecated publishing compatibility facade.

The canonical local publishing implementation lives in
:mod:`wp_log_parser.service_mode` and is re-exported by
:mod:`wp_log_parser.service`.  This module remains for older integrations that
imported ``wp_log_parser.publishing`` directly; new code should call the service
layer.
"""

from typing import Any

from .config import AppConfig
from .fetcher import fetch_post, normalize_post_date
from .parser import parse_post_content
from .service import publish_post as _publish_post
from .service import publish_once as _publish_once
from . import service_mode as _service_mode
from .source_metadata import attach_source_metadata


def publish_post(config: AppConfig, post_id: int, verbose: bool = False) -> dict[str, Any] | None:
    """Publish one WordPress post via the canonical service-layer pipeline.

    The assignments keep old monkeypatch seams working while still delegating
    all implementation to :mod:`wp_log_parser.service_mode`.
    """
    _service_mode.fetch_post = fetch_post
    _service_mode.normalize_post_date = normalize_post_date
    _service_mode.parse_post_content = parse_post_content
    _service_mode.attach_source_metadata = attach_source_metadata
    return _publish_post(config, post_id=post_id, verbose=verbose)


def publish_recent(config: AppConfig, days: int, verbose: bool = False) -> dict[str, Any]:
    """Publish recent posts via the canonical service-layer pipeline."""
    return _publish_once(config, days=days, verbose=verbose)
