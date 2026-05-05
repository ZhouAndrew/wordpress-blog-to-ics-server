from wp_log_parser.setup_wizard import (
    mask_secret,
    prompt_choice,
    prompt_executable,
    prompt_int,
    prompt_post_selection,
    prompt_yes_no,
    run_setup_wizard,
    select_post_id,
)


def test_mask_secret():
    assert mask_secret("abcd") == "****"
    assert mask_secret("abcdef") == "ab**ef"


def test_prompt_yes_no_accepts_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _=None: "")
    assert prompt_yes_no("Q", "E", True) is True


def test_prompt_choice_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _=None: "2")
    assert prompt_choice("Q", "E", ["wpcli", "rest"], "wpcli") == "rest"


def test_prompt_executable_accepts_valid_command(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _=None: "wp")
    monkeypatch.setattr("wp_log_parser.setup_wizard.shutil.which", lambda value: "/usr/bin/wp" if value == "wp" else None)
    assert prompt_executable("Q", "E", "wp") == "wp"


def test_prompt_executable_retries_for_missing_command(monkeypatch, tmp_path):
    script = tmp_path / "wp"
    script.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    script.chmod(0o755)
    values = iter(["missing-command", str(script)])
    monkeypatch.setattr("builtins.input", lambda _=None: next(values))
    monkeypatch.setattr("wp_log_parser.setup_wizard.shutil.which", lambda _value: None)
    assert prompt_executable("Q", "E", "wp") == str(script)


def test_prompt_executable_accepts_valid_path(monkeypatch, tmp_path):
    script = tmp_path / "python3"
    script.write_text("#!/bin/sh\necho python\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr("builtins.input", lambda _=None: str(script))
    monkeypatch.setattr("wp_log_parser.setup_wizard.shutil.which", lambda _value: None)
    assert prompt_executable("Q", "E", "python3") == str(script)


def test_prompt_executable_retries_for_invalid_path(monkeypatch, tmp_path):
    bad = tmp_path / "not-executable"
    bad.write_text("#!/bin/sh\necho bad\n", encoding="utf-8")
    good = tmp_path / "good-executable"
    good.write_text("#!/bin/sh\necho good\n", encoding="utf-8")
    good.chmod(0o755)
    values = iter([str(bad), str(good)])
    monkeypatch.setattr("builtins.input", lambda _=None: next(values))
    monkeypatch.setattr("wp_log_parser.setup_wizard.shutil.which", lambda _value: None)
    assert prompt_executable("Q", "E", "python3") == str(good)


def test_prompt_int_retries(monkeypatch):
    values = iter(["abc", "5"])
    monkeypatch.setattr("builtins.input", lambda _=None: next(values))
    assert prompt_int("Q", "E", 1) == 5


def test_prompt_post_selection_by_index(monkeypatch):
    posts = [
        {"id": 10, "title": "Today", "date": "2026-04-12", "status": "publish"},
        {"id": 11, "title": "Yesterday", "date": "2026-04-11", "status": "draft"},
    ]
    monkeypatch.setattr("builtins.input", lambda _=None: "2")
    assert prompt_post_selection("Q", "E", posts) == 11


def test_prompt_post_selection_by_id(monkeypatch):
    posts = [
        {"id": 10, "title": "Today", "date": "2026-04-12", "status": "publish"},
        {"id": 11, "title": "Yesterday", "date": "2026-04-11", "status": "draft"},
    ]
    monkeypatch.setattr("builtins.input", lambda _=None: "10")
    assert prompt_post_selection("Q", "E", posts) == 10


def test_select_post_id_uses_config_count(monkeypatch):
    class DummyConfig:
        post_selection_count = 7

    posts = [
        {"id": 99, "title": "Latest", "date": "2026-01-02", "status": "publish"},
        {"id": 10, "title": "Oldest", "date": "2026-01-01", "status": "publish"},
    ]
    captured = {}

    def fake_list_posts(config, per_page=None):
        captured["per_page"] = per_page
        return posts

    monkeypatch.setattr("wp_log_parser.setup_wizard.list_posts", fake_list_posts)
    monkeypatch.setattr("builtins.input", lambda _=None: "")

    assert select_post_id(DummyConfig()) == 99
    assert captured["per_page"] == 7


def test_wizard_summary_masks_caldav_password(monkeypatch, tmp_path, capsys):
    values = iter([
        "", "", "", "", "", "", "", "", "", "", "", "", "y", "https://caldav.test/cal", "user", "uid.local", "1", "n"
    ])
    monkeypatch.setattr("builtins.input", lambda _=None: next(values))
    monkeypatch.setattr("getpass.getpass", lambda _=None: "secret-pass")
    monkeypatch.setattr("wp_log_parser.setup_wizard.prompt_executable", lambda *a, **k: "python3")
    monkeypatch.setattr("wp_log_parser.setup_wizard.prompt_existing_path", lambda *a, **k: ".")
    monkeypatch.setattr("wp_log_parser.setup_wizard.prompt_directory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_dependencies", lambda: [])
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_python_path", lambda _p: type("R", (), {"ok": True, "name": "python", "message": "ok", "details": ""})())
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_output_dir", lambda _p: type("R", (), {"ok": True, "name": "dir", "message": "ok", "details": ""})())
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_wp_cli", lambda _p: type("R", (), {"ok": True, "name": "wp", "message": "ok", "details": ""})())
    monkeypatch.setattr("wp_log_parser.setup_wizard.validate_wordpress_path", lambda _p: type("R", (), {"ok": True, "name": "wp_path", "message": "ok", "details": ""})())
    run_setup_wizard(str(tmp_path / "config.json"))
    out = capsys.readouterr().out
    assert "secret-pass" not in out
