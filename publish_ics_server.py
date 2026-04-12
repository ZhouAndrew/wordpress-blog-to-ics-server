#!/usr/bin/env python3
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


BLOCK_RE = re.compile(
    r"<!--\s+wp:([a-zA-Z0-9_/:-]+)(?:\s+\{.*?\})?\s+-->(.*?)<!--\s+/wp:\1\s+-->",
    re.DOTALL,
)
PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
TIME_RE = re.compile(r"^\s*(\d{1,2}):([0-5]\d)\b(.*)$", re.DOTALL)


@dataclass
class LogEntry:
    start_dt: datetime
    end_dt: datetime
    summary: str
    raw: str
    status: str


class Logger:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def info(self, msg: str) -> None:
        print(f"[{self._ts()}] [INFO] {msg}")

    def ok(self, msg: str) -> None:
        print(f"[{self._ts()}] [OK] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[{self._ts()}] [WARN] {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"[{self._ts()}] [ERROR] {msg}", file=sys.stderr)

    def debug(self, msg: str) -> None:
        if self.verbose:
            print(f"[{self._ts()}] [DEBUG] {msg}")


def load_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd: List[str], log: Logger) -> str:
    log.debug("RUN " + " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"STDERR:\n{result.stderr.strip()}"
        )
    return result.stdout


def require_wpcli(config: Dict[str, Any], log: Logger) -> Tuple[str, str]:
    mode = config.get("wordpress_mode")
    if mode != "wpcli":
        raise ValueError(
            f"Unsupported wordpress_mode={mode!r}; only 'wpcli' is supported"
        )

    wp_cli_path = config.get("wp_cli_path", "wp")
    if shutil.which(wp_cli_path) is None:
        raise FileNotFoundError(f"wp-cli not found: {wp_cli_path}")

    wp_path = config.get("wp_path")
    if not wp_path:
        raise ValueError("Missing 'wp_path' in config")

    if not Path(wp_path).exists():
        raise FileNotFoundError(f"WordPress path not found: {wp_path}")

    log.ok(f"wp-cli ready: {wp_cli_path}")
    log.ok(f"WordPress path ready: {wp_path}")
    return wp_cli_path, wp_path


def strip_html(text: str) -> str:
    return html.unescape(TAG_RE.sub("", text)).strip()


def parse_dt_local(s: str, tz_name: str) -> datetime:
    naive = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    if ZoneInfo and tz_name:
        return naive.replace(tzinfo=ZoneInfo(tz_name))
    return naive


def get_now(tz_name: str) -> datetime:
    if ZoneInfo and tz_name:
        return datetime.now(ZoneInfo(tz_name))
    return datetime.now()


def wp_list_recent_posts(
    config: Dict[str, Any],
    days: int,
    tz_name: str,
    log: Logger,
) -> List[Dict[str, Any]]:
    wp_cli_path, wp_path = require_wpcli(config, log)
    cmd = [
        wp_cli_path,
        "post",
        "list",
        "--post_type=post",
        "--post_status=publish",
        "--fields=ID,post_title,post_date,post_status",
        "--format=json",
        f"--path={wp_path}",
    ]
    raw = run_cmd(cmd, log).strip()
    data = json.loads(raw) if raw else []

    now = get_now(tz_name)
    cutoff = now - timedelta(days=days)

    posts: List[Dict[str, Any]] = []
    for item in data:
        post_date_raw = str(item.get("post_date", "")).strip()
        if not post_date_raw:
            continue
        try:
            post_dt = parse_dt_local(post_date_raw, tz_name)
        except ValueError:
            log.warn(f"Skipping post with invalid post_date: {post_date_raw}")
            continue

        if post_dt >= cutoff:
            posts.append(
                {
                    "id": int(item["ID"]),
                    "title": str(item.get("post_title", "")),
                    "post_date": post_date_raw,
                    "status": str(item.get("post_status", "")),
                }
            )

    posts.sort(key=lambda x: x["post_date"], reverse=True)
    log.ok(f"Recent publish posts found in last {days} day(s): {len(posts)}")
    return posts


def wp_get_post(
    config: Dict[str, Any],
    post_id: int,
    log: Logger,
) -> Dict[str, Any]:
    wp_cli_path, wp_path = require_wpcli(config, log)
    cmd = [
        wp_cli_path,
        "post",
        "get",
        str(post_id),
        "--fields=ID,post_title,post_date,post_content,post_status",
        "--format=json",
        f"--path={wp_path}",
    ]
    raw = run_cmd(cmd, log).strip()
    data = json.loads(raw)
    return {
        "id": int(data["ID"]),
        "title": str(data.get("post_title", "")),
        "post_date": str(data.get("post_date", "")),
        "post_content": str(data.get("post_content", "")),
        "status": str(data.get("post_status", "")),
    }


def extract_blocks(post_content: str) -> List[Tuple[str, str]]:
    return [(name, inner) for name, inner in BLOCK_RE.findall(post_content)]


def extract_paragraph_text(block_html: str) -> str:
    m = PARAGRAPH_RE.search(block_html)
    if not m:
        return ""
    return strip_html(m.group(1))


def parse_entries(
    post_content: str,
    post_date: str,
    timezone_name: str,
    default_last_event_minutes: int,
    allow_empty_summary: bool,
    auto_cross_midnight: bool,
    log: Logger,
) -> Tuple[List[LogEntry], List[Dict[str, str]]]:
    base_dt = parse_dt_local(post_date, timezone_name)
    blocks = extract_blocks(post_content)

    raw_entries: List[Dict[str, Any]] = []
    ignored: List[Dict[str, str]] = []

    previous_minutes: Optional[int] = None
    day_offset = 0

    for idx, (block_name, inner_html) in enumerate(blocks, start=1):
        if block_name != "paragraph":
            ignored.append(
                {"index": str(idx), "block": block_name, "reason": "unsupported_block_type"}
            )
            continue

        text = extract_paragraph_text(inner_html)
        if not text:
            ignored.append(
                {"index": str(idx), "block": block_name, "reason": "empty_paragraph"}
            )
            continue

        m = TIME_RE.match(text)
        if not m:
            ignored.append(
                {
                    "index": str(idx),
                    "block": block_name,
                    "reason": "no_leading_time",
                    "text": text,
                }
            )
            continue

        hour, minute, tail = m.groups()
        summary = tail.strip(" \t-–—:：").strip()

        if not summary and not allow_empty_summary:
            ignored.append(
                {
                    "index": str(idx),
                    "block": block_name,
                    "reason": "empty_summary",
                    "text": text,
                }
            )
            continue

        total_minutes = int(hour) * 60 + int(minute)
        if previous_minutes is not None and total_minutes < previous_minutes:
            if auto_cross_midnight:
                day_offset += 1
            else:
                ignored.append(
                    {
                        "index": str(idx),
                        "block": block_name,
                        "reason": "time_goes_backwards",
                        "text": text,
                    }
                )
                continue

        start_dt = base_dt.replace(
            hour=int(hour),
            minute=int(minute),
            second=0,
            microsecond=0,
        ) + timedelta(days=day_offset)

        raw_entries.append(
            {
                "start_dt": start_dt,
                "summary": summary,
                "raw": text,
            }
        )
        previous_minutes = total_minutes

    entries: List[LogEntry] = []
    for i, item in enumerate(raw_entries):
        start_dt = item["start_dt"]
        summary = item["summary"]
        raw = item["raw"]

        if i + 1 < len(raw_entries):
            end_dt = raw_entries[i + 1]["start_dt"]
            status = "ready"
        else:
            end_dt = start_dt + timedelta(minutes=default_last_event_minutes)
            status = "inferred_last_event"

        entries.append(
            LogEntry(
                start_dt=start_dt,
                end_dt=end_dt,
                summary=summary,
                raw=raw,
                status=status,
            )
        )

    return entries, ignored


def escape_ics_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def fold_ics_line(line: str, limit: int = 75) -> List[str]:
    if len(line) <= limit:
        return [line]
    parts = [line[:limit]]
    remaining = line[limit:]
    while remaining:
        parts.append(" " + remaining[: limit - 1])
        remaining = remaining[limit - 1 :]
    return parts


def format_ics_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.strftime("%Y%m%dT%H%M%S")
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics(entries: List[LogEntry], calendar_name: str) -> str:
    now_utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wp_log_parser//Published Local ICS Server//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(calendar_name)}",
    ]

    for entry in entries:
        uid = f"{uuid.uuid4()}@wp-log-parser"
        event_lines = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_utc}",
            f"DTSTART:{format_ics_dt(entry.start_dt)}",
            f"DTEND:{format_ics_dt(entry.end_dt)}",
            f"SUMMARY:{escape_ics_text(entry.summary)}",
            f"DESCRIPTION:{escape_ics_text(entry.raw)}",
            "END:VEVENT",
        ]
        for line in event_lines:
            lines.extend(fold_ics_line(line))

    lines.append("END:VCALENDAR")
    lines.append("")
    return "\r\n".join(lines)


def safe_slug(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[^\w\-.]+", "_", text, flags=re.UNICODE)
    return text.strip("_")[:80] or "untitled"


def parse_base_url(url: str) -> Tuple[str, int, str]:
    u = urlparse(url)
    if not u.scheme or not u.netloc:
        raise ValueError(f"Invalid ics_base_url: {url}")
    host = u.hostname or "0.0.0.0"
    port = u.port or (443 if u.scheme == "https" else 80)
    path = u.path.rstrip("/") or ""
    return host, port, path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def publish_once(
    config: Dict[str, Any],
    publish_dir: Path,
    recent_days: int,
    tz_name: str,
    public_base_url: str,
    log: Logger,
) -> None:
    log.info("Starting publish cycle")
    posts = wp_list_recent_posts(config, recent_days, tz_name, log)

    default_last_event_minutes = int(config.get("default_last_event_minutes", 10))
    allow_empty_summary = bool(config.get("allow_empty_summary", False))
    auto_cross_midnight = bool(config.get("auto_cross_midnight", True))
    save_ignored_blocks = bool(config.get("save_ignored_blocks", True))

    index_items: List[Dict[str, Any]] = []
    published_count = 0
    skipped_count = 0

    for post_meta in posts:
        post_id = post_meta["id"]
        try:
            post = wp_get_post(config, post_id, log)
            entries, ignored = parse_entries(
                post_content=post["post_content"],
                post_date=post["post_date"],
                timezone_name=tz_name,
                default_last_event_minutes=default_last_event_minutes,
                allow_empty_summary=allow_empty_summary,
                auto_cross_midnight=auto_cross_midnight,
                log=log,
            )

            if not entries:
                skipped_count += 1
                log.warn(f"Skipped post {post_id}: no valid timed entries")
                continue

            date_part = post["post_date"].split(" ")[0]
            slug = safe_slug(post["title"])
            ics_name = f"{date_part}_post_{post_id}_{slug}.ics"
            ics_path = publish_dir / ics_name

            ics_text = build_ics(entries, f"WordPress Log {post_id}: {post['title']}")
            write_text(ics_path, ics_text)

            ignored_name = f"{date_part}_post_{post_id}_{slug}.ignored.json"
            if save_ignored_blocks:
                write_text(
                    publish_dir / ignored_name,
                    json.dumps(ignored, ensure_ascii=False, indent=2),
                )

            item = {
                "post_id": post_id,
                "title": post["title"],
                "post_date": post["post_date"],
                "ics_file": ics_name,
                "ics_url": f"{public_base_url.rstrip('/')}/{ics_name}",
                "entry_count": len(entries),
                "ignored_block_count": len(ignored),
            }
            index_items.append(item)
            published_count += 1
            log.ok(
                f"Published post {post_id}: {ics_name} "
                f"(entries={len(entries)}, ignored={len(ignored)})"
            )

        except Exception as exc:
            skipped_count += 1
            log.error(f"Failed post {post_id}: {exc}")

    index_items.sort(key=lambda x: x["post_date"], reverse=True)

    write_text(
        publish_dir / "index.json",
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "recent_days": recent_days,
                "published_count": published_count,
                "skipped_count": skipped_count,
                "items": index_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    html_lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>ICS Publish Index</title></head><body>",
        "<h1>ICS Publish Index</h1>",
        f"<p>Generated at: {html.escape(datetime.now(UTC).isoformat())}</p>",
        "<ul>",
    ]
    for item in index_items:
        html_lines.append(
            "<li>"
            f"<a href='{html.escape(item['ics_file'])}'>{html.escape(item['title'])}</a> "
            f"(ID: {item['post_id']}, date: {html.escape(item['post_date'])}, "
            f"entries: {item['entry_count']}, ignored: {item['ignored_block_count']})"
            "</li>"
        )
    html_lines.extend(["</ul>", "</body></html>"])
    write_text(publish_dir / "index.html", "\n".join(html_lines))

    log.ok(
        f"Publish cycle done: published={published_count}, skipped={skipped_count}, "
        f"index={publish_dir / 'index.json'}"
    )


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"[HTTP] {self.address_string()} - {format % args}"
        )


def serve_directory(directory: Path, host: str, port: int, log: Logger) -> None:
    class Handler(QuietHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

    httpd = ThreadingHTTPServer((host, port), Handler)
    log.ok(f"Serving {directory} at http://{host}:{port}/")
    httpd.serve_forever()


def publisher_loop(
    config: Dict[str, Any],
    publish_dir: Path,
    recent_days: int,
    interval_seconds: int,
    tz_name: str,
    public_base_url: str,
    log: Logger,
) -> None:
    while True:
        cycle_started = time.time()
        try:
            publish_once(
                config=config,
                publish_dir=publish_dir,
                recent_days=recent_days,
                tz_name=tz_name,
                public_base_url=public_base_url,
                log=log,
            )
        except Exception as exc:
            log.error(f"Publish cycle failed: {exc}")

        elapsed = time.time() - cycle_started
        sleep_for = max(1, interval_seconds - int(elapsed))
        log.info(f"Sleeping {sleep_for}s before next cycle")
        time.sleep(sleep_for)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Periodically rebuild ICS files from WordPress posts and publish them locally."
    )
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--days", type=int, default=7, help="Publish recent posts from last N days")
    parser.add_argument("--interval", type=int, default=60, help="Refresh interval in seconds")
    parser.add_argument(
        "--publish-dir",
        default="./published_ics",
        help="Directory to store published ICS files",
    )
    parser.add_argument("--host", help="HTTP bind host; default from ics_base_url or 0.0.0.0")
    parser.add_argument("--port", type=int, help="HTTP bind port; default from ics_base_url")
    parser.add_argument("--public-base-url", help="Public base URL; default from config.ics_base_url")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = Logger(verbose=args.verbose)
    log.info("Starting publish_ics_server")

    config = load_config(args.config)
    tz_name = str(config.get("timezone", "UTC"))
    publish_dir = Path(args.publish_dir).resolve()

    config_base_url = str(config.get("ics_base_url", "http://0.0.0.0:5333/ics")).rstrip("/")
    public_base_url = (args.public_base_url or config_base_url).rstrip("/")

    base_host, base_port, base_path = parse_base_url(config_base_url)
    host = args.host or "0.0.0.0"
    port = args.port or base_port

    if base_path and not public_base_url.endswith(base_path):
        log.warn(
            f"public_base_url={public_base_url!r} does not end with config path {base_path!r}. "
            "Make sure your reverse proxy path matches."
        )

    publish_dir.mkdir(parents=True, exist_ok=True)
    log.ok(f"Publish directory ready: {publish_dir}")
    log.ok(f"Timezone: {tz_name}")
    log.ok(f"Public base URL: {public_base_url}")

    publisher = threading.Thread(
        target=publisher_loop,
        kwargs={
            "config": config,
            "publish_dir": publish_dir,
            "recent_days": args.days,
            "interval_seconds": args.interval,
            "tz_name": tz_name,
            "public_base_url": public_base_url,
            "log": log,
        },
        daemon=True,
    )
    publisher.start()

    serve_directory(
        directory=publish_dir,
        host=host,
        port=port,
        log=log,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")
        raise SystemExit(130)