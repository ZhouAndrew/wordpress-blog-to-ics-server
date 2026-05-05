from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import AppConfig
from .exceptions import (
    AuthenticationFailedError,
    MalformedResponseError,
    PostNotFoundError,
    WPCLIUnavailableError,
    WordPressPathError,
)
from .wordpress import list_posts_rest, list_posts_wpcli


@dataclass
class PostData:
    post_id: int
    title: str
    post_date: str
    post_content: str
    status: str


def _parse_post_date(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("post_date is empty")

    iso_candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported post_date format: {value}")


def normalize_post_date(value: str) -> str:
    return _parse_post_date(value).date().isoformat()


def _map_wpcli_error(stderr: str, *, post_id: int | None = None) -> Exception:
    message = stderr.strip() or "wp-cli command failed"
    lower = message.lower()
    if "invalid post id" in lower or "not found" in lower or "could not find" in lower:
        return PostNotFoundError(message if post_id is None else f"Post {post_id} not found: {message}")
    if "access denied" in lower or "authentication" in lower or "permission denied" in lower:
        return AuthenticationFailedError(message)
    return MalformedResponseError(message)


def _coerce_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MalformedResponseError(f"WordPress payload field {field_name} must be an integer") from exc


def _coerce_str(value: Any, field_name: str) -> str:
    if value is None:
        raise MalformedResponseError(f"WordPress payload missing {field_name}")
    if not isinstance(value, (str, int, float, bool)):
        raise MalformedResponseError(f"WordPress payload field {field_name} must be scalar")
    return str(value)


def _post_data_from_wpcli_payload(data: Any) -> PostData:
    if not isinstance(data, dict):
        raise MalformedResponseError("wp-cli payload must be an object")
    return PostData(
        post_id=_coerce_int(data.get("ID"), "ID"),
        title=_coerce_str(data.get("post_title", ""), "post_title"),
        post_date=_coerce_str(data.get("post_date"), "post_date"),
        post_content=_coerce_str(data.get("post_content"), "post_content"),
        status=_coerce_str(data.get("post_status", ""), "post_status"),
    )


def _post_data_from_rest_payload(payload: Any) -> PostData:
    if not isinstance(payload, dict):
        raise MalformedResponseError("REST payload must be an object")

    raw_title = payload.get("title", "")
    if isinstance(raw_title, dict):
        title = _coerce_str(raw_title.get("rendered", ""), "title.rendered")
    else:
        title = _coerce_str(raw_title, "title")

    content = payload.get("content")
    if not isinstance(content, dict) or "raw" not in content:
        raise MalformedResponseError("REST payload missing content.raw")

    return PostData(
        post_id=_coerce_int(payload.get("id"), "id"),
        title=title,
        post_date=_coerce_str(payload.get("date"), "date"),
        post_content=_coerce_str(content.get("raw"), "content.raw"),
        status=_coerce_str(payload.get("status", ""), "status"),
    )


def _fetch_post_wpcli(config: AppConfig, post_id: int) -> PostData:
    if shutil.which(config.wp_cli_path) is None:
        raise WPCLIUnavailableError(f"wp-cli command not found: {config.wp_cli_path}")
    if not Path(config.wp_path).exists():
        raise WordPressPathError(f"WordPress path does not exist: {config.wp_path}")

    cmd = [
        config.wp_cli_path,
        "post",
        "get",
        str(post_id),
        "--fields=ID,post_title,post_date,post_content,post_status",
        "--format=json",
        f"--path={config.wp_path}",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise _map_wpcli_error(proc.stderr, post_id=post_id)

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError("wp-cli returned invalid JSON") from exc

    return _post_data_from_wpcli_payload(data)


def _fetch_post_rest(config: AppConfig, post_id: int) -> PostData:
    try:
        import requests
    except Exception as exc:  # pragma: no cover
        raise MalformedResponseError("requests package is required for REST mode") from exc

    endpoint = f"{config.base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}?context=edit"
    response = requests.get(
        endpoint,
        auth=(config.username, config.app_password),
        verify=config.verify_ssl,
        timeout=20,
    )
    if response.status_code in {401, 403}:
        raise AuthenticationFailedError("REST authentication failed")
    if response.status_code == 404:
        raise PostNotFoundError(f"Post {post_id} not found")
    if response.status_code >= 400:
        raise MalformedResponseError(f"Unexpected REST status code: {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise MalformedResponseError("REST returned invalid JSON") from exc

    return _post_data_from_rest_payload(payload)


def fetch_post(config: AppConfig, post_id: int | None) -> PostData:
    if post_id is None:
        raise ValueError("--post-id is required")
    if config.wordpress_mode == "wpcli":
        return _fetch_post_wpcli(config, post_id)
    if config.wordpress_mode == "rest":
        return _fetch_post_rest(config, post_id)
    raise ValueError("wordpress_mode must be either 'wpcli' or 'rest'")


def find_today_post_id(config: AppConfig) -> int:
    from .wordpress import find_today_post_id_rest, find_today_post_id_wpcli

    if config.wordpress_mode == "wpcli":
        return find_today_post_id_wpcli(config.wp_path, config.wp_cli_path)
    if config.wordpress_mode == "rest":
        return find_today_post_id_rest(config.base_url, config.username, config.app_password, config.verify_ssl)
    raise ValueError("wordpress_mode must be either 'wpcli' or 'rest'")


def fetch_today_post(config: AppConfig) -> PostData:
    return fetch_post(config, find_today_post_id(config))


def list_recent_post_ids(config: AppConfig, days: int) -> list[int]:
    try:
        tz = ZoneInfo(config.timezone)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {config.timezone}") from exc
    now = datetime.now(tz)
    cutoff = now - timedelta(days=days)
    ids: list[int] = []
    seen_ids: set[int] = set()
    pagination_complete = True
    page = 1
    per_page = 100

    def _fetch_page(page: int, size: int) -> list[dict[str, str | int]]:
        if config.wordpress_mode == "wpcli":
            return list_posts_wpcli(config.wp_path, config.wp_cli_path, per_page=size, limit=None, page=page)
        return list_posts_rest(
            config.base_url,
            config.username,
            config.app_password,
            config.verify_ssl,
            per_page=size,
            limit=None,
            page=page,
        )

    while True:
        page_rows = _fetch_page(page, per_page)
        if not page_rows:
            break

        new_rows = 0
        crossed_cutoff = False
        for post in page_rows:
            post_id = int(post["id"])
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            new_rows += 1

            post_date = str(post.get("date", ""))
            if not post_date:
                continue
            dt = _parse_post_date(post_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            else:
                dt = dt.astimezone(tz)
            if dt >= cutoff:
                ids.append(post_id)
            else:
                crossed_cutoff = True
                break

        if crossed_cutoff:
            break
        if len(page_rows) < per_page:
            break
        if new_rows == 0:
            pagination_complete = False
            break
        page += 1

    if not pagination_complete:
        print("Warning: pagination reliability check failed; recent post window may be incomplete.")
    return ids
