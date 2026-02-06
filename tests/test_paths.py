"""Tests for agent_catalogue.paths module."""

from __future__ import annotations

from pathlib import Path

from agent_catalogue.paths import (
    get_agents_dir,
    get_cache_dir,
    get_context_dir,
    get_global_dir,
    get_keys_path,
    get_session_dir,
    get_sessions_dir,
)


class TestGlobalDir:
    def test_returns_dot_agent_catalogue_in_home(self):
        result = get_global_dir()
        assert result == Path.home() / ".agent-catalogue"

    def test_returns_path_instance(self):
        assert isinstance(get_global_dir(), Path)


class TestCacheDir:
    def test_returns_cache_subdir(self):
        result = get_cache_dir()
        assert result == Path.home() / ".agent-catalogue" / "cache"

    def test_is_child_of_global_dir(self):
        assert get_cache_dir().parent == get_global_dir()


class TestSessionsDir:
    def test_returns_sessions_subdir(self):
        result = get_sessions_dir()
        assert result == Path.home() / ".agent-catalogue" / "sessions"

    def test_is_child_of_global_dir(self):
        assert get_sessions_dir().parent == get_global_dir()


class TestSessionDir:
    def test_returns_named_subdir(self):
        result = get_session_dir("test-123")
        assert result == Path.home() / ".agent-catalogue" / "sessions" / "test-123"

    def test_sanitizes_path_traversal_dotdot(self):
        result = get_session_dir("../evil")
        assert ".." not in result.name
        # ".." -> "_" then "/" -> "_" produces "__evil"
        assert result.name == "__evil"

    def test_sanitizes_forward_slash(self):
        result = get_session_dir("foo/bar")
        assert "/" not in result.name
        assert result.name == "foo_bar"

    def test_sanitizes_backslash(self):
        result = get_session_dir("foo\\bar")
        assert "\\" not in result.name
        assert result.name == "foo_bar"

    def test_sanitizes_combined_traversal(self):
        result = get_session_dir("../../etc/passwd")
        # ".." replaced with "_", "/" replaced with "_"
        assert ".." not in str(result.name)
        assert "/" not in result.name

    def test_is_child_of_sessions_dir(self):
        result = get_session_dir("safe-id")
        assert result.parent == get_sessions_dir()


class TestKeysPath:
    def test_returns_keys_env_in_global_dir(self):
        result = get_keys_path()
        assert result == Path.home() / ".agent-catalogue" / "keys.env"

    def test_is_child_of_global_dir(self):
        assert get_keys_path().parent == get_global_dir()


class TestAgentsDir:
    def test_returns_existing_directory(self):
        result = get_agents_dir()
        assert result.exists(), f"agents dir should exist at {result}"

    def test_is_named_agents(self):
        assert get_agents_dir().name == "agents"


class TestContextDir:
    def test_returns_existing_directory(self):
        result = get_context_dir()
        assert result.exists(), f"context dir should exist at {result}"

    def test_is_named_context(self):
        assert get_context_dir().name == "context"
