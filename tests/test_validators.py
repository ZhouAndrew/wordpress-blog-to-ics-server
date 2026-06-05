import pytest

from wp_log_parser.validators import (
    validate_caldav_config,
    validate_output_dir_readonly,
    validate_python_path,
    validate_rest_credentials,
    validate_wp_cli,
)


class _Response:
    def __init__(self, status_code=200, payload=None, json_exc=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"id": 1, "name": "Alice"}
        self._json_exc = json_exc

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._payload


def test_validate_python_path_passes_for_python3():
    result = validate_python_path("python3")
    assert result.ok is True


def test_validate_wp_cli_fails_for_missing_binary():
    result = validate_wp_cli("definitely-not-a-real-wp-binary")
    assert result.ok is False


def test_validate_rest_credentials_uses_authenticated_endpoint_and_verify_ssl(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(payload={"id": 4, "name": "Alice"})

    monkeypatch.setattr("requests.get", fake_get)

    result = validate_rest_credentials("https://wp.example", "alice", "secret", False)

    assert result.ok is True
    assert calls == [
        (
            "https://wp.example/wp-json/wp/v2/users/me?context=edit",
            {"auth": ("alice", "secret"), "verify": False, "timeout": 10},
        )
    ]


def test_validate_rest_credentials_rejects_missing_credentials_without_request(monkeypatch):
    def fail_get(*_args, **_kwargs):
        raise AssertionError("requests.get should not be called")

    monkeypatch.setattr("requests.get", fail_get)

    result = validate_rest_credentials("https://wp.example", "", "secret", True)

    assert result.ok is False
    assert "username" in result.message


def test_validate_rest_credentials_rejects_authentication_failure(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: _Response(status_code=401))

    result = validate_rest_credentials("https://wp.example", "alice", "wrong", True)

    assert result.ok is False
    assert "authentication failed" in result.message.lower()


def test_validate_rest_credentials_reports_connectivity_failure(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("requests.get", fake_get)

    result = validate_rest_credentials("https://wp.example", "alice", "secret", True)

    assert result.ok is False
    assert "connectivity failure" in result.message
    assert result.details == "boom"


@pytest.mark.parametrize("response", [_Response(payload=[]), _Response(json_exc=ValueError("bad json"))])
def test_validate_rest_credentials_reports_malformed_response(monkeypatch, response):
    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: response)

    result = validate_rest_credentials("https://wp.example", "alice", "secret", True)

    assert result.ok is False
    assert "Malformed REST response" in result.message


def test_validate_caldav_config_accepts_valid_values(tmp_path):
    idx_path = tmp_path / "caldav-sync-index.json"
    result = validate_caldav_config(
        "https://caldav.example.com/user/calendar",
        "alice",
        "secret",
        "example.com",
        str(idx_path),
        required=True,
    )
    assert result.ok is True


def test_validate_caldav_config_rejects_invalid_domain(tmp_path):
    idx_path = tmp_path / "caldav-sync-index.json"
    result = validate_caldav_config(
        "https://caldav.example.com/user/calendar",
        "alice",
        "secret",
        "bad domain",
        str(idx_path),
        required=True,
    )
    assert result.ok is False


def test_validate_output_dir_readonly_reports_missing_without_creating(tmp_path):
    missing = tmp_path / "does-not-exist"
    result = validate_output_dir_readonly(str(missing))
    assert result.ok is False
    assert result.message == "Directory is missing"
    assert missing.exists() is False
