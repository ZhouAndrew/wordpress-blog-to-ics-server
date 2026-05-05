from pathlib import Path


def test_sync_layer_does_not_generate_raw_vcalendar() -> None:
    sync_dir = Path('wp_log_parser/sync')
    offenders = []
    for py_file in sync_dir.rglob('*.py'):
        text = py_file.read_text(encoding='utf-8')
        if 'BEGIN:VCALENDAR' in text:
            offenders.append(py_file.as_posix())
    assert offenders == []
