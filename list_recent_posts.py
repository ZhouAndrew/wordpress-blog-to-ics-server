#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def load_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def require_wpcli(config: Dict[str, Any]) -> str:
    wordpress_mode = config.get("wordpress_mode")
    if wordpress_mode != "wpcli":
        raise ValueError(
            f"Unsupported wordpress_mode: {wordpress_mode!r}. "
            "This script currently supports only 'wpcli'."
        )

    wp_cli_path = config.get("wp_cli_path", "wp")
    if shutil.which(wp_cli_path) is None:
        raise FileNotFoundError(f"wp-cli not found in PATH: {wp_cli_path}")

    wp_path = config.get("wp_path")
    if not wp_path:
        raise ValueError("Missing 'wp_path' in config.json")

    if not Path(wp_path).exists():
        raise FileNotFoundError(f"WordPress path does not exist: {wp_path}")

    return wp_cli_path


def run_wp_cli_json(wp_cli_path: str, wp_path: str) -> List[Dict[str, Any]]:
    cmd = [
        wp_cli_path,
        "post",
        "list",
        "--post_type=post",
        "--fields=ID,post_title,post_date,post_status",
        "--format=json",
        f"--path={wp_path}",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        raise RuntimeError(
            "wp-cli command failed.\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDERR:\n{result.stderr.strip()}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Failed to parse wp-cli JSON output.\n"
            f"Raw output:\n{stdout}"
        ) from exc

    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected wp-cli output type: {type(data).__name__}")

    return data


def parse_wp_datetime(value: str) -> Optional[datetime]:
    """
    wp-cli usually returns something like:
    2026-04-11 07:45:03
    """
    if not value:
        return None

    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            # Treat WordPress local datetime as naive.
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def filter_recent_posts(posts: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    filtered: List[Dict[str, Any]] = []

    for post in posts:
        status = str(post.get("post_status", "")).strip()
        post_date_raw = str(post.get("post_date", "")).strip()
        post_dt = parse_wp_datetime(post_date_raw)

        if post_dt is None:
            continue

        if post_dt >= cutoff:
            filtered.append(
                {
                    "id": post.get("ID"),
                    "title": post.get("post_title", ""),
                    "date": post_date_raw,
                    "status": status,
                }
            )

    filtered.sort(
        key=lambda x: parse_wp_datetime(str(x["date"])) or datetime.min,
        reverse=True,
    )
    return filtered


def print_human(posts: List[Dict[str, Any]], days: int) -> None:
    print(f"Recent posts in the last {days} day(s):")
    if not posts:
        print("(none)")
        return

    for idx, post in enumerate(posts, start=1):
        print(
            f"{idx:>3}) {post['date']} [{post['status']}] "
            f"{post['title']} (ID: {post['id']})"
        )


def print_jsonl(posts: List[Dict[str, Any]]) -> None:
    for post in posts:
        print(
            json.dumps(
                {
                    "id": post["id"],
                    "title": post["title"],
                    "date": post["date"],
                    "status": post["status"],
                },
                ensure_ascii=False,
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List recent WordPress posts by title and ID."
    )
    parser.add_argument(
        "--config",
        default="./config.json",
        help="Path to config.json",
    )
    parser.add_argument(
        "--days",
        "-n",
        type=int,
        default=7,
        help="List posts from the last N days (default: 7)",
    )
    parser.add_argument(
        "--format",
        choices=["human", "jsonl"],
        default="human",
        help="Output format: human or jsonl",
    )

    args = parser.parse_args()

    if args.days < 0:
        eprint("Error: --days must be >= 0")
        return 2

    try:
        config = load_config(args.config)
        wp_cli_path = require_wpcli(config)
        wp_path = config["wp_path"]

        posts = run_wp_cli_json(wp_cli_path, wp_path)
        recent_posts = filter_recent_posts(posts, args.days)

        if args.format == "human":
            print_human(recent_posts, args.days)
        else:
            print_jsonl(recent_posts)

        return 0

    except Exception as exc:
        eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())