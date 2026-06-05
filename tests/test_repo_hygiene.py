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
