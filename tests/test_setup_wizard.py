from wp_log_parser.setup_wizard import mask_secret, prompt_choice, prompt_int, prompt_yes_no


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
