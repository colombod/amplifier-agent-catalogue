"""Tests for agent_catalogue.provider_utils (pure-logic helpers only)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_catalogue.provider_utils import _resolve_config_value, _should_show_field

# -- _should_show_field -----------------------------------------------------


class TestShouldShowField:
    """Test the show_when conditional-visibility logic."""

    def test_true_when_no_show_when(self):
        field: dict[str, Any] = {"id": "api_key", "prompt": "Key?"}
        assert _should_show_field(field, {}) is True

    def test_true_when_show_when_is_none(self):
        field: dict[str, Any] = {"id": "x", "prompt": "X?", "show_when": None}
        assert _should_show_field(field, {}) is True

    def test_exact_match_true(self):
        field: dict[str, Any] = {
            "id": "api_key",
            "prompt": "Key?",
            "show_when": {"auth": "api_key"},
        }
        assert _should_show_field(field, {"auth": "api_key"}) is True

    def test_exact_match_false(self):
        field: dict[str, Any] = {
            "id": "api_key",
            "prompt": "Key?",
            "show_when": {"auth": "api_key"},
        }
        assert _should_show_field(field, {"auth": "rbac"}) is False

    def test_exact_match_case_insensitive(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"mode": "Advanced"},
        }
        assert _should_show_field(field, {"mode": "advanced"}) is True

    def test_contains_pattern_true(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"url": "contains:azure"},
        }
        assert _should_show_field(field, {"url": "https://my-azure-endpoint.com"}) is True

    def test_contains_pattern_false(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"url": "contains:azure"},
        }
        assert _should_show_field(field, {"url": "https://api.openai.com"}) is False

    def test_not_contains_pattern_true(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"url": "not_contains:azure"},
        }
        assert _should_show_field(field, {"url": "https://api.openai.com"}) is True

    def test_not_contains_pattern_false(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"url": "not_contains:azure"},
        }
        assert _should_show_field(field, {"url": "https://azure.example.com"}) is False

    def test_startswith_pattern_true(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"url": "startswith:https://"},
        }
        assert _should_show_field(field, {"url": "https://example.com"}) is True

    def test_startswith_pattern_false(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"url": "startswith:https://"},
        }
        assert _should_show_field(field, {"url": "http://example.com"}) is False

    def test_missing_collected_key_treated_as_empty(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"auth": "api_key"},
        }
        # "auth" not in collected -> actual becomes ""
        assert _should_show_field(field, {}) is False

    def test_multiple_conditions_all_must_pass(self):
        field: dict[str, Any] = {
            "id": "x",
            "prompt": "X?",
            "show_when": {"auth": "api_key", "provider": "azure"},
        }
        # Both conditions met
        assert _should_show_field(field, {"auth": "api_key", "provider": "azure"}) is True
        # Only one met
        assert _should_show_field(field, {"auth": "api_key", "provider": "openai"}) is False

    def test_empty_show_when_dict_returns_true(self):
        field: dict[str, Any] = {"id": "x", "prompt": "X?", "show_when": {}}
        assert _should_show_field(field, {"anything": "whatever"}) is True


# -- _resolve_config_value --------------------------------------------------


class TestResolveConfigValue:
    def test_resolves_env_placeholder(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MY_SECRET", "s3cret")
        assert _resolve_config_value("${MY_SECRET}") == "s3cret"

    def test_returns_none_for_missing_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NOPE_KEY", raising=False)
        assert _resolve_config_value("${NOPE_KEY}") is None

    def test_returns_non_placeholder_string_as_is(self):
        assert _resolve_config_value("literal-value") == "literal-value"

    def test_returns_non_string_as_is(self):
        assert _resolve_config_value(42) == 42
        assert _resolve_config_value(True) is True
        assert _resolve_config_value(None) is None

    def test_partial_placeholder_not_resolved(self):
        # Only exact ${VAR} pattern is resolved (starts with ${ and ends with })
        result = _resolve_config_value("prefix-${VAR}")
        assert result == "prefix-${VAR}"

    def test_env_var_with_special_chars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("KEY_WITH_EQUALS", "a=b&c=d")
        assert _resolve_config_value("${KEY_WITH_EQUALS}") == "a=b&c=d"

    def test_empty_env_var_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        # os.environ.get returns "" which is truthy check... let's verify
        result = _resolve_config_value("${EMPTY_VAR}")
        assert result == ""
