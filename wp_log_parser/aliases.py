from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ICS_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_post_(\d+)_.*\.ics$")


def today_date_str(timezone_name: str) -> str:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {timezone_name}") from exc
    return datetime.now(tz).strftime("%Y-%m-%d")


def find_today_ics_candidates(publish_dir: Path, today: str) -> list[Path]:
    if not publish_dir.exists():
        raise FileNotFoundError(f"Publish directory not found: {publish_dir}")
    if not publish_dir.is_dir():
        raise NotADirectoryError(f"Publish directory is not a directory: {publish_dir}")
    matches: list[Path] = []
    for path in publish_dir.iterdir():
        if not path.is_file():
            continue
        if path.name in {"today.ics", "latest.ics", "all.ics"}:
            continue
        m = ICS_FILE_RE.match(path.name)
        if m and m.group(1) == today:
            matches.append(path)
    return sorted(matches, key=_candidate_sort_key, reverse=True)


def _candidate_sort_key(path: Path) -> tuple[str, int, str]:
    match = ICS_FILE_RE.match(path.name)
    if match:
        return match.group(1), int(match.group(2)), path.name
    return "", -1, path.name


def select_today_ics(candidates: list[Path], preferred_post_id: int | None = None) -> Path:
    if not candidates:
        raise FileNotFoundError("No ICS file found for today")
    if preferred_post_id is not None:
        for p in candidates:
            m = ICS_FILE_RE.match(p.name)
            if m and int(m.group(2)) == preferred_post_id:
                return p
    return candidates[0]


def select_today_ics_from_post_metadata(
    candidates: list[Path],
    posts_metadata: list[dict[str, object]] | None,
) -> Path | None:
    if not candidates or not posts_metadata:
        return None
    candidate_map: dict[int, Path] = {}
    for path in candidates:
        match = ICS_FILE_RE.match(path.name)
        if match:
            candidate_map[int(match.group(2))] = path
    if not candidate_map:
        return None

    sortable: list[tuple[str, str, int]] = []
    for item in posts_metadata:
        post_id = item.get("id")
        if not isinstance(post_id, int) or post_id not in candidate_map:
            continue
        modified = str(item.get("modified_gmt") or "")
        published = str(item.get("date") or "")
        sortable.append((modified, published, post_id))
    if not sortable:
        return None
    _, _, newest_post_id = max(sortable)
    return candidate_map[newest_post_id]


def generate_today_ics(
    publish_dir: str,
    timezone_name: str,
    preferred_post_id: int | None = None,
    mode: str = "copy",
    target_name: str = "today.ics",
) -> Path:
    if mode not in {"copy", "symlink"}:
        raise ValueError(f"Invalid alias mode: {mode}. Expected 'copy' or 'symlink'.")
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
