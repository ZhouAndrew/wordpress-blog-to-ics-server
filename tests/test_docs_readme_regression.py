from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_readme_contains_current_phase_2_commands_and_status_statements() -> None:
    readme = _read("README.md")

    required_snippets = [
        "Pre-alpha / internal validation build",
        "python -m wp_log_parser init-config --config ./config.json",
        "python -m wp_log_parser init-config --wizard --config ./config.json",
        "python -m wp_log_parser validate-config --config ./config.json",
        "python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213",
        "python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose",
        "python -m wp_log_parser publish-ics --config ./config.json",
        "python -m wp_log_parser publish-ics --config ./config.json --verbose",
        "python -m wp_log_parser update-today-ics --config ./config.json",
        "python -m wp_log_parser update-today-ics --config ./config.json --verbose",
        "python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 60",
        "python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 300 --host 127.0.0.1 --port 5333",
        "python -m wp_log_parser sync-caldav --config ./config.json --dry-run",
        "python -m wp_log_parser sync-caldav --config ./config.json",
        "./install.sh",
        "./run.sh",
        "## Parser contract",
        "## Deterministic `today.ics` behavior",
        "## Generated artifacts",
        "## Root scripts and package service status",
        "## Validation Matrix (Docs ↔ Scripts ↔ CLI)",
        "## Known Limitations (Current)",
        "`run.sh` opens the interactive TTY app only",
        "`post-to-ics` requires `--post-id`",
        "`publish-ics` defaults to a 7-day window",
        "REST mode requires authenticated application-password access",
        "18:00–18:23 Dinner",
        "18:00—18:23 Dinner",
        "18:00~18:23 Dinner",
        "`YYYY-MM-DD_post_<post_id>_<slug>.ics`",
        "`today.ics`",
        "`index.json`",
        "`index.html`",
        "`*.ignored.json`",
    ]

    missing = [snippet for snippet in required_snippets if snippet not in readme]
    assert not missing, f"README missing expected snippets: {missing}"


def test_getting_started_contains_fresh_clone_verification_flow() -> None:
    guide = _read("GETTING_STARTED.md")

    required_snippets = [
        "python -m pip install -r requirements.txt",
        "python -m wp_log_parser init-config --config ./config.json",
        "python -m wp_log_parser validate-config --config ./config.json",
        "python -m wp_log_parser post-to-ics --config ./config.json --post-id 10213 --verbose",
        "python -m wp_log_parser publish-ics --config ./config.json --verbose",
        "python -m wp_log_parser update-today-ics --config ./config.json --verbose",
        "python -m wp_log_parser run-ics-service --config ./config.json --days 7 --interval 60",
        "REST mode requires authenticated WordPress application-password access",
        "Supported range formats",
        "Deterministic today behavior",
        "`index.json`",
        "`index.html`",
        "`*.ignored.json`",
    ]

    missing = [snippet for snippet in required_snippets if snippet not in guide]
    assert not missing, f"GETTING_STARTED missing expected snippets: {missing}"


def test_docs_do_not_recommend_legacy_root_prototype_scripts() -> None:
    docs = {
        "README.md": _read("README.md"),
        "GETTING_STARTED.md": _read("GETTING_STARTED.md"),
    }
    forbidden = [
        "python export_post_id_to_ics_verbose.py",
        "python parser_exporter.py",
        "python publish_ics_server.py",
        "python run_ics_service.py",
        "python update_today_ics.py",
        "python list_recent_posts.py",
    ]

    found = {
        path: [snippet for snippet in forbidden if snippet in text]
        for path, text in docs.items()
    }
    found = {path: snippets for path, snippets in found.items() if snippets}
    assert not found, f"Docs still recommend legacy root prototype scripts: {found}"
