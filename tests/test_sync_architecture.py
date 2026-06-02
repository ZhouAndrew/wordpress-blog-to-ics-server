from pathlib import Path


def test_sync_layer_does_not_generate_raw_vcalendar() -> None:
    sync_dir = Path('wp_log_parser/sync')
    offenders = []
    for py_file in sync_dir.rglob('*.py'):
        text = py_file.read_text(encoding='utf-8')
        if 'BEGIN:VCALENDAR' in text:
            offenders.append(py_file.as_posix())
    assert offenders == []


def test_cli_operational_commands_call_service_layer_not_pipeline_modules() -> None:
    cli_text = Path("wp_log_parser/cli.py").read_text(encoding="utf-8")
    forbidden_snippets = [
        "from .fetcher import",
        "from .parser import",
        "from .ics_exporter import",
        "from .timeline import",
        "parse_post_content(",
        "write_post_ics(",
        "apply_timeline(",
    ]
    offenders = [snippet for snippet in forbidden_snippets if snippet in cli_text]
    assert offenders == []


def test_service_layer_owns_operational_cli_entrypoints() -> None:
    service_text = Path("wp_log_parser/service.py").read_text(encoding="utf-8")
    for function_name in (
        "fetch_post_payload",
        "parse_post",
        "export_ics_from_json_file",
        "run_today_pipeline",
        "post_to_ics",
        "publish_ics",
        "update_today_ics",
        "run_ics_service",
    ):
        assert f"def {function_name}" in service_text
