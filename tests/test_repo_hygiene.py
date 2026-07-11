from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


FORBIDDEN_BASENAMES = {
    "config.json",
    "secrets.json",
    ".env",
    ".env.local",
    "today.ics",
    "index.json",
    "index.html",
}

FORBIDDEN_EXACT_PATHS = {
    "errors/last_run.json",
    "FETCH_HEAD",
}

FORBIDDEN_SUFFIXES = (
    ".secrets.json",
    ".token",
    ".tokens",
)


def _is_forbidden_tracked_file(path: str) -> bool:
    return (
        path in FORBIDDEN_EXACT_PATHS
        or Path(path).name in FORBIDDEN_BASENAMES
        or path.endswith(FORBIDDEN_SUFFIXES)
    )


def _forbidden_tracked_files(tracked: set[str]) -> list[str]:
    return sorted(path for path in tracked if _is_forbidden_tracked_file(path))


def _release_hygiene_pattern() -> re.Pattern[str]:
    script = Path("scripts/package-release.sh").read_text(encoding="utf-8")
    match = re.search(r"^FORBIDDEN_RELEASE_PATH_PATTERN='(.+)'$", script, re.MULTILINE)
    assert match is not None
    return re.compile(match.group(1))


def _normalize_archive_entry(entry: str, archive_prefix: str) -> str:
    if entry.startswith(archive_prefix):
        return entry[len(archive_prefix):]
    return entry


def _forbidden_release_paths(paths: list[str]) -> list[str]:
    pattern = _release_hygiene_pattern()
    return [path for path in paths if pattern.search(path)]


def test_forbidden_runtime_files_not_tracked() -> None:
    found = _forbidden_tracked_files(_tracked_files())
    assert not found, f"Forbidden runtime files are tracked: {found}"


def test_forbidden_runtime_file_policy_rejects_known_artifacts() -> None:
    rejected = _forbidden_tracked_files({
        "config.json",
        "nested/config.json",
        "secrets.json",
        "nested/secrets.json",
        ".env",
        "runtime/.env",
        ".env.local",
        "nested/.env.local",
        "today.ics",
        "output/today.ics",
        "index.json",
        "output/index.json",
        "index.html",
        "published_ics/index.html",
        "errors/last_run.json",
        "credentials/site.token",
        "credentials/site.tokens",
        "nested/private.secrets.json",
        "FETCH_HEAD",
    })
    assert rejected == [
        ".env",
        ".env.local",
        "FETCH_HEAD",
        "config.json",
        "credentials/site.token",
        "credentials/site.tokens",
        "errors/last_run.json",
        "index.html",
        "index.json",
        "nested/.env.local",
        "nested/config.json",
        "nested/private.secrets.json",
        "nested/secrets.json",
        "output/index.json",
        "output/today.ics",
        "published_ics/index.html",
        "runtime/.env",
        "secrets.json",
        "today.ics",
    ]


def test_forbidden_runtime_file_policy_allows_non_artifacts() -> None:
    allowed = {
        "example.config.json",
        "example.env",
        "docs/FETCH_HEAD",
        "wp_log_parser/parser.py",
        "README.md",
    }
    assert _forbidden_tracked_files(allowed) == []


def test_example_config_exists() -> None:
    assert Path("example.config.json").exists()


def test_root_compatibility_scripts_delegate_to_package_services() -> None:
    scripts = [
        Path("export_post_id_to_ics_verbose.py"),
        Path("publish_ics_server.py"),
        Path("update_today_ics.py"),
        Path("run_ics_service.py"),
        Path("list_recent_posts.py"),
    ]
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert "from wp_log_parser.service import" in text
        assert "subprocess" not in text
        assert "BEGIN:VCALENDAR" not in text


def test_release_packaging_pattern_rejects_forbidden_runtime_artifacts() -> None:
    forbidden = [
        "FETCH_HEAD",
        "config.json",
        "nested/config.json",
        "runtime/.env",
        "output/today.ics",
        "output/index.json",
        "published_ics/index.html",
        "errors/last_run.json",
    ]
    assert _forbidden_release_paths(forbidden) == forbidden


def test_release_packaging_pattern_allows_non_artifacts() -> None:
    allowed = [
        "docs/FETCH_HEAD",
        "example.config.json",
        "example.env",
        "wp_log_parser/parser.py",
        "README.md",
    ]
    assert _forbidden_release_paths(allowed) == []


def test_archive_prefix_normalization_rejects_archive_root_fetch_head() -> None:
    archive_prefix = "wordpress-blog-to-ics-server-v0.1.0-alpha/"
    archive_entries = [
        f"{archive_prefix}FETCH_HEAD",
        f"{archive_prefix}config.json",
        f"{archive_prefix}runtime/.env",
        f"{archive_prefix}output/index.json",
        f"{archive_prefix}errors/last_run.json",
    ]

    normalized = [_normalize_archive_entry(path, archive_prefix) for path in archive_entries]

    assert normalized == [
        "FETCH_HEAD",
        "config.json",
        "runtime/.env",
        "output/index.json",
        "errors/last_run.json",
    ]
    assert _forbidden_release_paths(normalized) == normalized


def test_archive_prefix_normalization_allows_nested_fetch_head() -> None:
    archive_prefix = "wordpress-blog-to-ics-server-v0.1.0-alpha/"
    archive_entries = [
        f"{archive_prefix}docs/FETCH_HEAD",
        f"{archive_prefix}example.config.json",
        f"{archive_prefix}example.env",
        f"{archive_prefix}wp_log_parser/parser.py",
    ]

    normalized = [_normalize_archive_entry(path, archive_prefix) for path in archive_entries]

    assert normalized == [
        "docs/FETCH_HEAD",
        "example.config.json",
        "example.env",
        "wp_log_parser/parser.py",
    ]
    assert _forbidden_release_paths(normalized) == []
