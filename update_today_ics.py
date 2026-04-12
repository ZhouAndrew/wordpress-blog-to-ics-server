#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


ICS_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_post_(\d+)_.*\.ics$")


class Logger:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def info(self, msg: str) -> None:
        print(f"[INFO] {msg}")

    def ok(self, msg: str) -> None:
        print(f"[OK] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[WARN] {msg}", file=sys.stderr)

    def debug(self, msg: str) -> None:
        if self.verbose:
            print(f"[DEBUG] {msg}")


def load_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def now_date_str(timezone_name: str) -> str:
    if ZoneInfo and timezone_name:
        return datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def find_today_candidates(publish_dir: Path, today: str, log: Logger) -> List[Path]:
    matches: List[Path] = []

    for path in publish_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in {"today.ics", "latest.ics", "all.ics"}:
            continue

        m = ICS_FILE_RE.match(path.name)
        if not m:
            continue

        file_date = m.group(1)
        if file_date == today:
            matches.append(path)

    matches.sort(key=lambda p: p.name, reverse=True)
    log.debug(f"Today candidates: {[p.name for p in matches]}")
    return matches


def choose_candidate(candidates: List[Path], preferred_post_id: Optional[int], log: Logger) -> Path:
    if not candidates:
        raise FileNotFoundError("No ICS file found for today")

    if preferred_post_id is not None:
        for path in candidates:
            m = ICS_FILE_RE.match(path.name)
            if m and int(m.group(2)) == preferred_post_id:
                log.ok(f"Selected preferred post_id={preferred_post_id}: {path.name}")
                return path
        log.warn(f"Preferred post_id={preferred_post_id} not found among today's ICS files")

    selected = candidates[0]
    log.ok(f"Selected today's ICS: {selected.name}")
    return selected


def remove_if_exists(path: Path, log: Logger) -> None:
    if path.exists() or path.is_symlink():
        log.debug(f"Removing existing target: {path}")
        path.unlink()


def write_copy(src: Path, dst: Path, log: Logger) -> None:
    remove_if_exists(dst, log)
    shutil.copy2(src, dst)
    log.ok(f"Copied {src.name} -> {dst.name}")


def write_symlink(src: Path, dst: Path, log: Logger) -> None:
    remove_if_exists(dst, log)
    dst.symlink_to(src.name)
    log.ok(f"Symlinked {dst.name} -> {src.name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or update today.ics from published ICS files."
    )
    parser.add_argument("--config", default="./config.json")
    parser.add_argument("--publish-dir", default="./published_ics")
    parser.add_argument(
        "--mode",
        choices=["copy", "symlink"],
        default="copy",
        help="How to create today.ics",
    )
    parser.add_argument(
        "--today-name",
        default="today.ics",
        help="Output filename for today's alias",
    )
    parser.add_argument(
        "--post-id",
        type=int,
        help="Prefer a specific post ID if multiple ICS files exist for today",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = Logger(verbose=args.verbose)

    try:
        log.info("Loading config")
        config = load_config(args.config)
        timezone_name = str(config.get("timezone", "UTC"))
        log.ok(f"Timezone: {timezone_name}")

        publish_dir = Path(args.publish_dir).resolve()
        if not publish_dir.exists():
            raise FileNotFoundError(f"Publish directory not found: {publish_dir}")
        log.ok(f"Publish directory: {publish_dir}")

        today = now_date_str(timezone_name)
        log.info(f"Today is: {today}")

        candidates = find_today_candidates(publish_dir, today, log)
        selected = choose_candidate(candidates, args.post_id, log)

        target = publish_dir / args.today_name
        if args.mode == "symlink":
            write_symlink(selected, target, log)
        else:
            write_copy(selected, target, log)

        print(
            json.dumps(
                {
                    "today": today,
                    "source_file": selected.name,
                    "target_file": target.name,
                    "mode": args.mode,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())