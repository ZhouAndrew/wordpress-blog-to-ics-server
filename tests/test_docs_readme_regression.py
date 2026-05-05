from pathlib import Path


def test_readme_contains_critical_commands_and_status_statements() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    required_snippets = [
        "./install.sh",
        "./run.sh",
        "python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213",
        "python -m wp_log_parser publish-ics --config ./config.json --days 7",
        "python -m wp_log_parser update-today-ics --config ./config.json",
        "python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333",
        "python -m wp_log_parser sync-caldav --config ./config.json --dry-run",
        "python -m wp_log_parser sync-caldav --config ./config.json",
        "## Validation Matrix (Docs ↔ Scripts ↔ CLI)",
        "## Known Limitations (Current)",
        "`run.sh` opens the interactive TTY app only",
        "`post-to-ics` requires `--post-id`",
        "`publish-ics` requires `--days`",
    ]

    missing = [snippet for snippet in required_snippets if snippet not in readme]
    assert not missing, f"README missing expected snippets: {missing}"
