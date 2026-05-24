from __future__ import annotations

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


def test_forbidden_runtime_files_not_tracked() -> None:
    tracked = _tracked_files()
    forbidden = {
        "config.json",
        "secrets.json",
        ".env",
        ".env.local",
        "today.ics",
        "index.json",
        "index.html",
    }
    found = sorted(forbidden & tracked)
    assert not found, f"Forbidden runtime files are tracked: {found}"


def test_example_config_exists() -> None:
    assert Path("example.config.json").exists()
