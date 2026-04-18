from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import AppConfig
from .exceptions import MalformedResponseError


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


def _fetch_post_wpcli(config: AppConfig, post_id: int) -> PostData:
    if shutil.which(config.wp_cli_path) is None:
        raise FileNotFoundError(f"wp-cli not found: {config.wp_cli_path}")
    if not Path(config.wp_path).exists():
        raise FileNotFoundError(f"WordPress path not found: {config.wp_path}")

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
        raise RuntimeError(proc.stderr.strip() or "wp-cli post get failed")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError("wp-cli returned invalid JSON") from exc

    return PostData(
        post_id=int(data["ID"]),
        title=str(data.get("post_title", "")),
        post_date=str(data.get("post_date", "")),
        post_content=str(data.get("post_content", "")),
        status=str(data.get("post_status", "")),
    )


def _fetch_post_rest(config: AppConfig, post_id: int) -> PostData:
    import requests

    endpoint = f"{config.base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}?context=edit"
    response = requests.get(
        endpoint,
        auth=(config.username, config.app_password),
        verify=config.verify_ssl,
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"REST post get failed: {response.status_code}")

    payload = response.json()
    title = ""
    if isinstance(payload.get("title"), dict):
        title = str(payload["title"].get("rendered", ""))
    else:
        title = str(payload.get("title", ""))

    return PostData(
        post_id=int(payload["id"]),
        title=title,
        post_date=str(payload.get("date", "")),
        post_content=str(payload["content"]["raw"]),
        status=str(payload.get("status", "")),
    )


def fetch_post(config: AppConfig, post_id: int) -> PostData:
    if post_id is None:
        raise ValueError("--post-id is required")
    if config.wordpress_mode == "wpcli":
        return _fetch_post_wpcli(config, post_id)
    return _fetch_post_rest(config, post_id)


def list_recent_post_ids(config: AppConfig, days: int) -> list[int]:
    from .service import list_posts

    try:
        tz = ZoneInfo(config.timezone)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {config.timezone}") from exc
    now = datetime.now(tz)
    cutoff = now - timedelta(days=days)
    ids: list[int] = []
    for post in list_posts(config, per_page=max(config.post_selection_count, 100)):
        post_date = str(post.get("date", ""))
        if not post_date:
            continue
        dt = _parse_post_date(post_date).replace(tzinfo=tz)
        if dt >= cutoff:
            ids.append(int(post["id"]))
    return ids
