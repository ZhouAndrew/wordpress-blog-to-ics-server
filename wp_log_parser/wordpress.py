from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

from .exceptions import (
    AuthenticationFailedError,
    MalformedResponseError,
    PostNotFoundError,
    WPCLIUnavailableError,
    WordPressPathError,
)


def sort_and_limit_posts(
    posts: list[dict[str, str | int]], limit: int | None = None
) -> list[dict[str, str | int]]:
    """
    Sort posts by date in ascending order (earliest → latest).
    If limit is specified, return only the most recent N posts.
    The returned list remains in ascending order with the latest post at the end.
    """
    sorted_posts = sorted(posts, key=lambda post: post.get("date", ""))
    if limit is not None and limit > 0:
        return sorted_posts[-limit:]
    return sorted_posts


def fetch_post_content_wpcli(post_id: int, wp_path: str, wp_cli_path: str = "wp") -> str:
    if shutil.which(wp_cli_path) is None:
        raise WPCLIUnavailableError(f"wp-cli command not found: {wp_cli_path}")
    if not Path(wp_path).exists():
        raise WordPressPathError(f"WordPress path does not exist: {wp_path}")

    cmd = [wp_cli_path, "post", "get", str(post_id), "--field=post_content", f"--path={wp_path}"]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if "Invalid post ID" in stderr or "not found" in stderr.lower():
            raise PostNotFoundError(stderr)
        raise MalformedResponseError(stderr or "Failed to fetch post content from wp-cli")
    return proc.stdout


def find_today_post_id_wpcli(wp_path: str, wp_cli_path: str = "wp") -> int:
    if shutil.which(wp_cli_path) is None:
        raise WPCLIUnavailableError(f"wp-cli command not found: {wp_cli_path}")
    if not Path(wp_path).exists():
        raise WordPressPathError(f"WordPress path does not exist: {wp_path}")

    today = date.today().isoformat()
    cmd = [
        wp_cli_path,
        "post",
        "list",
        "--post_type=post",
        f"--date_query=after={today} 00:00:00,before={today} 23:59:59,inclusive=1",
        "--orderby=date",
        "--order=asc",
        "--format=json",
        f"--path={wp_path}",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MalformedResponseError(proc.stderr.strip() or "Failed to list posts")

    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError("wp-cli returned invalid JSON") from exc

    if not rows:
        raise PostNotFoundError(f"No post found for date {today}")
    return int(rows[0]["ID"])


def list_posts_wpcli(wp_path: str, wp_cli_path: str = "wp", per_page: int = 20, limit: int | None = None) -> list[dict[str, str | int]]:
    if shutil.which(wp_cli_path) is None:
        raise WPCLIUnavailableError(f"wp-cli command not found: {wp_cli_path}")
    if not Path(wp_path).exists():
        raise WordPressPathError(f"WordPress path does not exist: {wp_path}")

    cmd = [
        wp_cli_path,
        "post",
        "list",
        "--post_type=post",
        "--post_status=any",
        "--orderby=date",
        "--order=asc",
        "--fields=ID,post_title,post_date,post_status",
        f"--format=json",
        f"--path={wp_path}",
        f"--posts_per_page={per_page}",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MalformedResponseError(proc.stderr.strip() or "Failed to list posts")

    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError("wp-cli returned invalid JSON") from exc

    posts = [
        {
            "id": int(row["ID"]),
            "title": row.get("post_title", "") or "",
            "date": row.get("post_date", "") or "",
            "status": row.get("post_status", "") or "",
        }
        for row in rows
    ]
    return sort_and_limit_posts(posts, limit=limit)


def fetch_post_content_rest(
    base_url: str,
    post_id: int,
    username: str,
    app_password: str,
    verify_ssl: bool = True,
) -> str:
    try:
        import requests
    except Exception as exc:  # pragma: no cover
        raise MalformedResponseError("requests package is required for REST mode") from exc

    endpoint = f"{base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}?context=edit"
    response = requests.get(endpoint, auth=(username, app_password), verify=verify_ssl, timeout=20)

    if response.status_code in {401, 403}:
        raise AuthenticationFailedError("REST authentication failed")
    if response.status_code == 404:
        raise PostNotFoundError(f"Post {post_id} not found")
    if response.status_code >= 400:
        raise MalformedResponseError(f"Unexpected REST status code: {response.status_code}")

    payload = response.json()
    try:
        return payload["content"]["raw"]
    except (TypeError, KeyError) as exc:
        raise MalformedResponseError("REST payload missing content.raw") from exc


def list_posts_rest(
    base_url: str,
    username: str,
    app_password: str,
    verify_ssl: bool = True,
    per_page: int = 20,
    limit: int | None = None,
) -> list[dict[str, str | int]]:
    try:
        import requests
    except Exception as exc:  # pragma: no cover
        raise MalformedResponseError("requests package is required for REST mode") from exc

    endpoint = (
        f"{base_url.rstrip('/')}/wp-json/wp/v2/posts?context=edit&status=any&orderby=date&order=asc&per_page={per_page}"
    )
    response = requests.get(endpoint, auth=(username, app_password), verify=verify_ssl, timeout=20)

    if response.status_code in {401, 403}:
        raise AuthenticationFailedError("REST authentication failed")
    if response.status_code >= 400:
        raise MalformedResponseError(f"Unexpected REST status code: {response.status_code}")

    payload = response.json()
    posts = []
    for item in payload:
        title = ""
        if isinstance(item.get("title"), dict):
            title = item["title"].get("rendered", "")
        else:
            title = str(item.get("title", ""))

        posts.append(
            {
                "id": int(item["id"]),
                "title": title,
                "date": item.get("date", "") or "",
                "status": item.get("status", "") or "",
            }
        )
    return sort_and_limit_posts(posts, limit=limit)


def find_today_post_id_rest(
    base_url: str,
    username: str,
    app_password: str,
    verify_ssl: bool = True,
) -> int:
    try:
        import requests
    except Exception as exc:  # pragma: no cover
        raise MalformedResponseError("requests package is required for REST mode") from exc

    today = date.today().isoformat()
    endpoint = (
        f"{base_url.rstrip('/')}/wp-json/wp/v2/posts?after={today}T00:00:00"
        f"&before={today}T23:59:59&context=edit&per_page=1"
    )
    response = requests.get(endpoint, auth=(username, app_password), verify=verify_ssl, timeout=20)

    if response.status_code in {401, 403}:
        raise AuthenticationFailedError("REST authentication failed")
    if response.status_code >= 400:
        raise MalformedResponseError(f"Unexpected REST status code: {response.status_code}")

    payload = response.json()
    if not payload:
        raise PostNotFoundError(f"No post found for date {today}")
    if "id" not in payload[0]:
        raise MalformedResponseError("REST payload missing id")
    return int(payload[0]["id"])
