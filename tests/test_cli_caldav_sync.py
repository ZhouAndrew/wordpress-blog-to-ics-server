from __future__ import annotations

from wp_log_parser import cli
from wp_log_parser.config import AppConfig


def test_cli_parser_includes_sync_caldav_command() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["sync-caldav", "--config", "./config.json", "--dry-run", "--debug"])
    assert args.command == "sync-caldav"
    assert args.dry_run is True
    assert args.debug is True


def test_cli_sync_caldav_executes_engine(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "config_exists", lambda path: True)
    monkeypatch.setattr(cli, "load_config", lambda path: AppConfig())
    monkeypatch.setattr(cli, "_print_validation", lambda config, require_caldav=False: True)
    monkeypatch.setattr(
        cli,
        "run_caldav_sync",
        lambda config, dry_run=False, debug_events=None: {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "cancelled": 0,
            "skipped": 0,
            "changed_posts": 0,
            "dry_run": dry_run,
            "index_path": config.caldav_index_path,
        },
    )

    code = cli.main(["sync-caldav", "--config", "./config.json", "--dry-run"])
    out = capsys.readouterr().out

    assert code == 0
    assert '"dry_run": true' in out
