from wp_log_parser.setup_wizard import mask_secret, prompt_choice, prompt_int, prompt_post_selection, prompt_yes_no, select_post_id


def test_mask_secret():
    assert mask_secret("abcd") == "****"
    assert mask_secret("abcdef") == "ab**ef"


def test_prompt_yes_no_accepts_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _=None: "")
    assert prompt_yes_no("Q", "E", True) is True


def test_prompt_choice_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _=None: "2")
    assert prompt_choice("Q", "E", ["wpcli", "rest"], "wpcli") == "rest"


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
        {"id": 10, "title": "Oldest", "date": "2026-01-01", "status": "publish"},
        {"id": 99, "title": "Latest", "date": "2026-01-02", "status": "publish"},
    ]
    captured = {}

    def fake_list_posts(config, per_page=None):
        captured["per_page"] = per_page
        return posts

    monkeypatch.setattr("wp_log_parser.setup_wizard.list_posts", fake_list_posts)
    monkeypatch.setattr("builtins.input", lambda _=None: "")

    assert select_post_id(DummyConfig()) == 99
    assert captured["per_page"] == 7
