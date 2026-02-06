"""Tests for agent_catalogue.settings module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from agent_catalogue.settings import (
    DEFAULT_SETTINGS,
    _deep_merge,
    _resolve_env_vars,
    has_provider_configured,
    load_settings,
    save_settings,
)

# -- _deep_merge -----------------------------------------------------------


class TestDeepMerge:
    def test_overlay_wins_on_scalar(self):
        base: dict[str, Any] = {"a": 1}
        _deep_merge(base, {"a": 2})
        assert base["a"] == 2

    def test_adds_new_keys(self):
        base: dict[str, Any] = {"a": 1}
        _deep_merge(base, {"b": 2})
        assert base == {"a": 1, "b": 2}

    def test_recurses_into_dicts(self):
        base: dict[str, Any] = {"nested": {"x": 1, "y": 2}}
        _deep_merge(base, {"nested": {"y": 99, "z": 3}})
        assert base["nested"] == {"x": 1, "y": 99, "z": 3}

    def test_replaces_lists_entirely(self):
        base: dict[str, Any] = {"items": [1, 2, 3]}
        _deep_merge(base, {"items": [4, 5]})
        assert base["items"] == [4, 5]

    def test_overlay_dict_replaces_scalar(self):
        base: dict[str, Any] = {"a": "string"}
        _deep_merge(base, {"a": {"nested": True}})
        assert base["a"] == {"nested": True}

    def test_empty_overlay_is_noop(self):
        base: dict[str, Any] = {"a": 1}
        _deep_merge(base, {})
        assert base == {"a": 1}

    def test_deep_copy_prevents_mutation(self):
        overlay_list = [1, 2, 3]
        base: dict[str, Any] = {}
        _deep_merge(base, {"items": overlay_list})
        overlay_list.append(4)
        assert base["items"] == [1, 2, 3]


# -- _resolve_env_vars ------------------------------------------------------


class TestResolveEnvVars:
    def test_resolves_simple_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MY_VAR", "hello")
        data: dict[str, Any] = {"key": "${MY_VAR}"}
        _resolve_env_vars(data)
        assert data["key"] == "hello"

    def test_resolves_default_when_var_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        data: dict[str, Any] = {"key": "${MISSING_VAR:fallback}"}
        _resolve_env_vars(data)
        assert data["key"] == "fallback"

    def test_resolves_var_ignoring_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SET_VAR", "real")
        data: dict[str, Any] = {"key": "${SET_VAR:fallback}"}
        _resolve_env_vars(data)
        assert data["key"] == "real"

    def test_missing_var_no_default_becomes_empty(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("GONE", raising=False)
        data: dict[str, Any] = {"key": "${GONE}"}
        _resolve_env_vars(data)
        assert data["key"] == ""

    def test_handles_nested_dicts(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("INNER", "resolved")
        data: dict[str, Any] = {"outer": {"inner": "${INNER}"}}
        _resolve_env_vars(data)
        assert data["outer"]["inner"] == "resolved"

    def test_handles_lists(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ITEM", "val")
        data: dict[str, Any] = {"items": ["${ITEM}", "literal"]}
        _resolve_env_vars(data)
        assert data["items"] == ["val", "literal"]

    def test_non_string_values_untouched(self):
        data: dict[str, Any] = {"num": 42, "flag": True, "nothing": None}
        _resolve_env_vars(data)
        assert data == {"num": 42, "flag": True, "nothing": None}

    def test_partial_placeholder_in_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HOST", "example.com")
        data: dict[str, Any] = {"url": "https://${HOST}/api"}
        _resolve_env_vars(data)
        assert data["url"] == "https://example.com/api"


# -- load_settings ----------------------------------------------------------


class TestLoadSettings:
    def test_returns_defaults_when_no_files(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """When no settings files exist, load_settings returns DEFAULT_SETTINGS."""
        # Point all path functions to non-existent files
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: tmp_path / "global.yaml",
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_project_settings_path",
            lambda: tmp_path / "project.yaml",
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_local_settings_path",
            lambda: tmp_path / "local.yaml",
        )
        result = load_settings()
        assert result["providers"] == DEFAULT_SETTINGS["providers"]
        assert result["server"]["port"] == DEFAULT_SETTINGS["server"]["port"]

    def test_global_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        global_file = tmp_path / "global.yaml"
        global_file.write_text(yaml.dump({"server": {"port": 9999}}))
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: global_file,
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_project_settings_path",
            lambda: tmp_path / "nope.yaml",
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_local_settings_path",
            lambda: tmp_path / "nope2.yaml",
        )
        result = load_settings()
        assert result["server"]["port"] == 9999

    def test_local_overrides_project(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        proj = tmp_path / "project.yaml"
        proj.write_text(yaml.dump({"server": {"host": "project-host"}}))
        local = tmp_path / "local.yaml"
        local.write_text(yaml.dump({"server": {"host": "local-host"}}))
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: tmp_path / "nope.yaml",
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_project_settings_path",
            lambda: proj,
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_local_settings_path",
            lambda: local,
        )
        result = load_settings()
        assert result["server"]["host"] == "local-host"

    def test_env_vars_resolved_in_result(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("TEST_HOST", "resolved.example.com")
        global_file = tmp_path / "global.yaml"
        global_file.write_text(yaml.dump({"server": {"host": "${TEST_HOST}"}}))
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: global_file,
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_project_settings_path",
            lambda: tmp_path / "nope.yaml",
        )
        monkeypatch.setattr(
            "agent_catalogue.settings.get_local_settings_path",
            lambda: tmp_path / "nope2.yaml",
        )
        result = load_settings()
        assert result["server"]["host"] == "resolved.example.com"


# -- save_settings ----------------------------------------------------------


class TestSaveSettings:
    def test_writes_valid_yaml(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        out = tmp_path / "settings.yaml"
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: out,
        )
        save_settings({"server": {"port": 1234}}, scope="global")
        assert out.exists()
        loaded = yaml.safe_load(out.read_text())
        assert loaded["server"]["port"] == 1234

    def test_returns_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        out = tmp_path / "settings.yaml"
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: out,
        )
        result = save_settings({"x": 1}, scope="global")
        assert result == out

    def test_creates_parent_dirs(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        out = tmp_path / "sub" / "dir" / "settings.yaml"
        monkeypatch.setattr(
            "agent_catalogue.settings.get_global_settings_path",
            lambda: out,
        )
        save_settings({"x": 1}, scope="global")
        assert out.exists()

    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError, match="Unknown scope"):
            save_settings({}, scope="bogus")


# -- has_provider_configured ------------------------------------------------


class TestHasProviderConfigured:
    def test_false_for_empty_providers(self):
        assert has_provider_configured({"providers": []}) is False

    def test_false_for_missing_providers_key(self):
        assert has_provider_configured({}) is False

    def test_true_when_providers_exist(self):
        settings = {"providers": [{"module": "provider-anthropic", "config": {}}]}
        assert has_provider_configured(settings) is True
