#!/usr/bin/env python3
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    end_dt: Optional[datetime]
    summary: str
    raw: str
    status: str


class Logger:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def info(self, msg: str) -> None:
        print(f"[INFO] {msg}")

    def ok(self, msg: str) -> None:
        print(f"[OK] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[WARN] {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"[ERROR] {msg}", file=sys.stderr)

    def debug(self, msg: str) -> None:
        if self.verbose:
            print(f"[DEBUG] {msg}")


def load_config(path: str, log: Logger) -> Dict[str, Any]:
    log.info(f"Loading config: {path}")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    log.ok("Config loaded")
    log.debug(f"Config keys: {', '.join(sorted(data.keys()))}")
    return data


def run_cmd(cmd: List[str], log: Logger) -> str:
    log.info("Running command:")
    log.debug(" ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    log.debug(f"Return code: {result.returncode}")
    if result.stdout.strip():
        preview = result.stdout.strip()
        if len(preview) > 300:
            preview = preview[:300] + "...(truncated)"
        log.debug(f"STDOUT preview: {preview}")

    if result.stderr.strip():
        preview = result.stderr.strip()
        if len(preview) > 300:
            preview = preview[:300] + "...(truncated)"
        log.debug(f"STDERR preview: {preview}")

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"STDERR:\n{result.stderr.strip()}"
        )

    log.ok("Command completed")
    return result.stdout


def require_wpcli(config: Dict[str, Any], log: Logger) -> Tuple[str, str]:
    mode = config.get("wordpress_mode")
    log.info(f"Checking wordpress mode: {mode!r}")
    if mode != "wpcli":
        raise ValueError(
            f"Unsupported wordpress_mode={mode!r}. This script currently supports only 'wpcli'."
        )

    wp_cli_path = config.get("wp_cli_path", "wp")
    log.info(f"Checking wp-cli executable: {wp_cli_path}")
    if shutil.which(wp_cli_path) is None:
        raise FileNotFoundError(f"wp-cli not found: {wp_cli_path}")
    log.ok("wp-cli executable found")

    wp_path = config.get("wp_path")
    if not wp_path:
        raise ValueError("Missing 'wp_path' in config")

    log.info(f"Checking WordPress path: {wp_path}")
    if not Path(wp_path).exists():
        raise FileNotFoundError(f"WordPress path not found: {wp_path}")
    log.ok("WordPress path exists")

    return wp_cli_path, wp_path


def fetch_post_data_wpcli(config: Dict[str, Any], post_id: int, log: Logger) -> Dict[str, str]:
    wp_cli_path, wp_path = require_wpcli(config, log)

    log.info(f"Fetching post via wp-cli: post_id={post_id}")
    fields = "ID,post_title,post_date,post_content,post_status"
    cmd = [
        wp_cli_path,
        "post",
        "get",
        str(post_id),
        f"--path={wp_path}",
        f"--fields={fields}",
        "--format=json",
    ]
    raw = run_cmd(cmd, log).strip()
    if not raw:
        raise RuntimeError("wp post get returned empty output")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON returned by wp-cli:\n{raw}") from exc

    required = ["ID", "post_title", "post_date", "post_content"]
    for key in required:
        if key not in data:
            raise RuntimeError(f"wp-cli response missing field: {key}")

    log.ok(
        f"Fetched post: ID={data['ID']}, title={data.get('post_title', '')!r}, "
        f"date={data.get('post_date', '')}, status={data.get('post_status', '')}"
    )
    log.debug(f"post_content length: {len(str(data.get('post_content', '')))}")

    return {
        "post_id": str(data["ID"]),
        "title": str(data.get("post_title", "")),
        "date": str(data.get("post_date", "")),
        "content": str(data.get("post_content", "")),
        "status": str(data.get("post_status", "")),
    }


def strip_html(text: str) -> str:
    no_tags = TAG_RE.sub("", text)
    return html.unescape(no_tags).strip()


def normalize_time(hour: str, minute: str) -> str:
    return f"{int(hour):02d}:{minute}"


def parse_post_date(post_date: str, log: Logger) -> datetime:
    post_date = post_date.strip()
    log.info(f"Parsing post_date: {post_date}")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(post_date, fmt)
            log.ok(f"Parsed post_date with format: {fmt}")
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unsupported post_date format: {post_date}")


def extract_gutenberg_blocks(post_content: str, log: Logger) -> List[Tuple[str, str]]:
    blocks = [(block_name, inner_html) for block_name, inner_html in BLOCK_RE.findall(post_content)]
    log.info(f"Extracted Gutenberg blocks: {len(blocks)}")
    if log.verbose:
        for i, (name, _) in enumerate(blocks[:20], start=1):
            log.debug(f"Block {i}: {name}")
        if len(blocks) > 20:
            log.debug(f"... plus {len(blocks) - 20} more blocks")
    return blocks


def extract_paragraph_text(block_html: str) -> str:
    m = PARAGRAPH_RE.search(block_html)
    if not m:
        return ""
    return strip_html(m.group(1))


def parse_log_entries(
    post_content: str,
    post_date: datetime,
    default_last_event_minutes: int,
    allow_empty_summary: bool,
    auto_cross_midnight: bool,
    log: Logger,
) -> Tuple[List[LogEntry], List[Dict[str, str]]]:
    blocks = extract_gutenberg_blocks(post_content, log)

    raw_entries: List[Dict[str, Any]] = []
    ignored_blocks: List[Dict[str, str]] = []

    current_day_offset = 0
    previous_minutes: Optional[int] = None

    log.info("Scanning blocks for timed paragraph entries")

    for index, (block_name, inner_html) in enumerate(blocks, start=1):
        if block_name != "paragraph":
            ignored_blocks.append(
                {"index": str(index), "block": block_name, "reason": "unsupported_block_type"}
            )
            log.debug(f"Ignored block #{index}: {block_name} (unsupported)")
            continue

        text = extract_paragraph_text(inner_html)
        if not text:
            ignored_blocks.append(
                {"index": str(index), "block": block_name, "reason": "empty_paragraph"}
            )
            log.debug(f"Ignored block #{index}: empty paragraph")
            continue

        m = TIME_RE.match(text)
        if not m:
            ignored_blocks.append(
                {
                    "index": str(index),
                    "block": block_name,
                    "reason": "no_leading_time",
                    "text": text,
                }
            )
            log.debug(f"Ignored block #{index}: no leading time -> {text!r}")
            continue

        hour, minute, tail = m.groups()
        hhmm = normalize_time(hour, minute)
        summary = tail.strip(" \t-–—:：").strip()

        if not summary and not allow_empty_summary:
            ignored_blocks.append(
                {
                    "index": str(index),
                    "block": block_name,
                    "reason": "empty_summary",
                    "text": text,
                }
            )
            log.debug(f"Ignored block #{index}: empty summary after time -> {text!r}")
            continue

        total_minutes = int(hour) * 60 + int(minute)

        if previous_minutes is not None and total_minutes < previous_minutes:
            if auto_cross_midnight:
                current_day_offset += 1
                log.debug(
                    f"Block #{index}: detected time rollback {hhmm}, "
                    f"crossing midnight, day_offset={current_day_offset}"
                )
            else:
                ignored_blocks.append(
                    {
                        "index": str(index),
                        "block": block_name,
                        "reason": "time_goes_backwards",
                        "text": text,
                    }
                )
                log.debug(f"Ignored block #{index}: time goes backwards -> {text!r}")
                continue

        start_dt = datetime(
            year=post_date.year,
            month=post_date.month,
            day=post_date.day,
            hour=int(hour),
            minute=int(minute),
        ) + timedelta(days=current_day_offset)

        raw_entries.append(
            {
                "start_dt": start_dt,
                "summary": summary,
                "raw": text,
            }
        )

        log.debug(
            f"Accepted block #{index}: start={start_dt.strftime('%Y-%m-%d %H:%M')}, "
            f"summary={summary!r}"
        )

        previous_minutes = total_minutes

    log.info(f"Accepted timed entries: {len(raw_entries)}")
    log.info(f"Ignored blocks: {len(ignored_blocks)}")

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

        log.debug(
            f"Built event #{i + 1}: "
            f"{start_dt.strftime('%Y-%m-%d %H:%M')} -> "
            f"{end_dt.strftime('%Y-%m-%d %H:%M')} | {summary!r} [{status}]"
        )

    return entries, ignored_blocks


def escape_ics_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def format_ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics(entries: List[LogEntry], calendar_name: str, log: Logger) -> str:
    log.info("Building ICS content")
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wp_log_parser//WordPress Daily Log Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(calendar_name)}",
    ]

    for i, entry in enumerate(entries, start=1):
        uid = f"{uuid.uuid4()}@wp-log-parser"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"DTSTART:{format_ics_dt(entry.start_dt)}",
                f"DTEND:{format_ics_dt(entry.end_dt)}",
                f"SUMMARY:{escape_ics_text(entry.summary)}",
                f"DESCRIPTION:{escape_ics_text(entry.raw)}",
                "END:VEVENT",
            ]
        )
        log.debug(f"Added VEVENT #{i}: {entry.summary!r}")

    lines.append("END:VCALENDAR")
    lines.append("")

    log.ok(f"ICS built with {len(entries)} VEVENT(s)")
    return "\r\n".join(lines)


def resolve_output_path(
    output: Optional[str],
    output_dir: str,
    post_id: int,
    post_title: str,
    post_date: str,
    log: Logger,
) -> Path:
    if output:
        path = Path(output)
        log.info(f"Using explicit output path: {path}")
        return path

    safe_title = re.sub(r"[^\w\-.]+", "_", post_title.strip(), flags=re.UNICODE).strip("_")
    safe_date = post_date.split(" ")[0]
    filename = f"{safe_date}_post_{post_id}"
    if safe_title:
        filename += f"_{safe_title[:60]}"
    filename += ".ics"

    path = Path(output_dir) / filename
    log.info(f"Using generated output path: {path}")
    return path


def print_entries(entries: List[LogEntry]) -> None:
    print("\nParsed entries:")
    for i, entry in enumerate(entries, start=1):
        print(
            f"{i:>3}) {entry.start_dt.strftime('%Y-%m-%d %H:%M')} "
            f"-> {entry.end_dt.strftime('%Y-%m-%d %H:%M')} | "
            f"{entry.summary} [{entry.status}]"
        )


def print_ignored(ignored_blocks: List[Dict[str, str]], limit: int = 20) -> None:
    print("\nIgnored blocks:")
    if not ignored_blocks:
        print("(none)")
        return

    for i, item in enumerate(ignored_blocks[:limit], start=1):
        text = item.get("text", "")
        if len(text) > 80:
            text = text[:80] + "...(truncated)"
        extra = f" | text={text!r}" if text else ""
        print(
            f"{i:>3}) index={item.get('index')} block={item.get('block')} "
            f"reason={item.get('reason')}{extra}"
        )

    if len(ignored_blocks) > limit:
        print(f"... {len(ignored_blocks) - limit} more ignored blocks")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a WordPress post by ID and export it to an ICS file."
    )
    parser.add_argument("--config", default="./config.json", help="Path to config.json")
    parser.add_argument("--post-id", type=int, required=True, help="WordPress post ID")
    parser.add_argument("--output", help="Output .ics file path")
    parser.add_argument("--print-summary", action="store_true", help="Print parsed entries")
    parser.add_argument("--print-ignored", action="store_true", help="Print ignored blocks")
    parser.add_argument("--verbose", action="store_true", help="Show detailed debug logs")
    args = parser.parse_args()

    log = Logger(verbose=args.verbose)

    try:
        log.info("Starting export_post_id_to_ics_verbose")
        config = load_config(args.config, log)

        post = fetch_post_data_wpcli(config, args.post_id, log)
        post_date = parse_post_date(post["date"], log)

        default_last_event_minutes = int(config.get("default_last_event_minutes", 10))
        allow_empty_summary = bool(config.get("allow_empty_summary", False))
        auto_cross_midnight = bool(config.get("auto_cross_midnight", True))
        output_dir = str(config.get("output_dir", "./output"))

        log.info(
            "Parser options: "
            f"default_last_event_minutes={default_last_event_minutes}, "
            f"allow_empty_summary={allow_empty_summary}, "
            f"auto_cross_midnight={auto_cross_midnight}"
        )

        entries, ignored_blocks = parse_log_entries(
            post_content=post["content"],
            post_date=post_date,
            default_last_event_minutes=default_last_event_minutes,
            allow_empty_summary=allow_empty_summary,
            auto_cross_midnight=auto_cross_midnight,
            log=log,
        )

        if not entries:
            raise RuntimeError("No valid timed log entries found in the post")

        calendar_name = f"WordPress Log Post {post['post_id']}: {post['title']}"
        ics_text = build_ics(entries, calendar_name, log)

        out_path = resolve_output_path(
            output=args.output,
            output_dir=output_dir,
            post_id=args.post_id,
            post_title=post["title"],
            post_date=post["date"],
            log=log,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        log.ok(f"Ensured output directory exists: {out_path.parent}")

        out_path.write_text(ics_text, encoding="utf-8", newline="")
        log.ok(f"Wrote ICS file: {out_path}")

        result = {
            "post_id": args.post_id,
            "title": post["title"],
            "post_date": post["date"],
            "output_file": str(out_path),
            "entry_count": len(entries),
            "ignored_block_count": len(ignored_blocks),
        }
        print("\nResult:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if args.print_summary:
            print_entries(entries)

        if args.print_ignored:
            print_ignored(ignored_blocks)

        log.ok("Done")
        return 0

    except Exception as exc:
        log.error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())