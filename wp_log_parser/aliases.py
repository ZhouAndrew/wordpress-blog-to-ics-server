from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ICS_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_post_(\d+)_.*\.ics$")


def today_date_str(timezone_name: str) -> str:
    return datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")


def find_today_ics_candidates(publish_dir: Path, today: str) -> list[Path]:
    matches: list[Path] = []
    for path in publish_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in {"today.ics", "latest.ics", "all.ics"}:
            continue
        m = ICS_FILE_RE.match(path.name)
        if m and m.group(1) == today:
            matches.append(path)
    return sorted(matches, key=lambda p: p.name, reverse=True)


def select_today_ics(candidates: list[Path], preferred_post_id: int | None = None) -> Path:
    if not candidates:
        raise FileNotFoundError("No ICS file found for today")
    if preferred_post_id is not None:
        for p in candidates:
            m = ICS_FILE_RE.match(p.name)
            if m and int(m.group(2)) == preferred_post_id:
                return p
    return candidates[0]


def generate_today_ics(
    publish_dir: str,
    timezone_name: str,
    preferred_post_id: int | None = None,
    mode: str = "copy",
    target_name: str = "today.ics",
) -> Path:
    root = Path(publish_dir)
    today = today_date_str(timezone_name)
    selected = select_today_ics(find_today_ics_candidates(root, today), preferred_post_id)
    target = root / target_name
    if target.exists() or target.is_symlink():
        target.unlink()
    if mode == "symlink":
        target.symlink_to(selected.name)
    else:
        shutil.copy2(selected, target)
    return target
