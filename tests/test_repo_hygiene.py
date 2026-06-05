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


def test_example_config_loads_with_current_schema() -> None:
    from wp_log_parser.config import load_config

    config = load_config("example.config.json")
    assert config.logs_dir == "./logs"
    assert config.overlap_policy in {"warn", "needs_review", "error"}
    assert config.review_entry_export_mode in {"include", "skip", "error"}


def test_docs_do_not_reference_root_prototypes_as_supported_entrypoints() -> None:
    docs = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ["README.md", "GETTING_STARTED.md"]
    )
    prototype_files = [
        "export_post_id_to_ics_verbose.py",
        "parser_exporter.py",
        "publish_ics_server.py",
        "run_ics_service.py",
        "update_today_ics.py",
        "list_recent_posts.py",
    ]
    offenders = [name for name in prototype_files if f"python {name}" in docs or f"./{name}" in docs]
    assert not offenders, f"Docs advertise root prototype entrypoints: {offenders}"
