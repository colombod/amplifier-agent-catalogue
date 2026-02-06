"""Tests for agent_catalogue.key_manager module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_catalogue.key_manager import KeyManager


@pytest.fixture()
def keys_path(tmp_path: Path) -> Path:
    """Return a temporary keys.env path (does NOT exist yet)."""
    return tmp_path / "keys.env"


@pytest.fixture()
def km(keys_path: Path) -> KeyManager:
    """KeyManager wired to a temp file."""
    return KeyManager(keys_path=keys_path)


class TestSaveKey:
    def test_creates_file_and_writes_key(self, km: KeyManager, keys_path: Path):
        km.save_key("MY_KEY", "secret123")
        assert keys_path.exists()
        content = keys_path.read_text()
        assert 'MY_KEY="secret123"' in content

    def test_updates_existing_key(self, km: KeyManager, keys_path: Path):
        km.save_key("MY_KEY", "old")
        km.save_key("MY_KEY", "new")
        content = keys_path.read_text()
        assert 'MY_KEY="new"' in content
        assert content.count("MY_KEY=") == 1

    def test_preserves_other_keys(self, km: KeyManager, keys_path: Path):
        km.save_key("KEY_A", "aaa")
        km.save_key("KEY_B", "bbb")
        content = keys_path.read_text()
        assert 'KEY_A="aaa"' in content
        assert 'KEY_B="bbb"' in content

    def test_sets_environ(self, km: KeyManager, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SAVE_TEST_KEY", raising=False)
        km.save_key("SAVE_TEST_KEY", "val")
        assert os.environ["SAVE_TEST_KEY"] == "val"

    def test_file_format_uses_quotes(self, km: KeyManager, keys_path: Path):
        km.save_key("QUOTED", "value")
        for line in keys_path.read_text().splitlines():
            if line.startswith("QUOTED"):
                assert line == 'QUOTED="value"'

    def test_keys_sorted_alphabetically(self, km: KeyManager, keys_path: Path):
        km.save_key("ZEBRA", "z")
        km.save_key("ALPHA", "a")
        lines = [ln for ln in keys_path.read_text().splitlines() if ln and not ln.startswith("#")]
        assert lines[0].startswith("ALPHA")
        assert lines[1].startswith("ZEBRA")


class TestLoadKeys:
    def test_populates_environ(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('LOAD_TEST="loaded_val"\n')
        monkeypatch.delenv("LOAD_TEST", raising=False)
        km.load_keys()
        assert os.environ["LOAD_TEST"] == "loaded_val"

    def test_does_not_overwrite_existing_env(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('EXISTING="from_file"\n')
        monkeypatch.setenv("EXISTING", "from_env")
        km.load_keys()
        assert os.environ["EXISTING"] == "from_env"

    def test_skips_if_file_missing(self, km: KeyManager, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        km.load_keys()  # should not raise
        assert "MISSING_KEY" not in os.environ

    def test_loads_only_once(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('ONCE_KEY="first"\n')
        monkeypatch.delenv("ONCE_KEY", raising=False)
        km.load_keys()
        assert os.environ["ONCE_KEY"] == "first"
        # Rewrite file and load again — should NOT reload
        keys_path.write_text('ONCE_KEY="second"\n')
        monkeypatch.delenv("ONCE_KEY", raising=False)
        km.load_keys()
        # Value should NOT be set again because _loaded flag is True
        assert os.environ.get("ONCE_KEY") is None or os.environ["ONCE_KEY"] != "second"

    def test_ignores_comments_and_blanks(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('# comment\n\nVALID="yes"\n')
        monkeypatch.delenv("VALID", raising=False)
        km.load_keys()
        assert os.environ["VALID"] == "yes"


class TestGetKey:
    def test_returns_env_value_first(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('PRIO="file"\n')
        monkeypatch.setenv("PRIO", "env")
        assert km.get_key("PRIO") == "env"

    def test_falls_back_to_file(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('FALLBACK="from_file"\n')
        monkeypatch.delenv("FALLBACK", raising=False)
        assert km.get_key("FALLBACK") == "from_file"

    def test_returns_none_when_absent(self, km: KeyManager, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NOPE", raising=False)
        assert km.get_key("NOPE") is None


class TestHasKey:
    def test_true_when_in_env(self, km: KeyManager, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HAS_ME", "1")
        assert km.has_key("HAS_ME") is True

    def test_true_when_in_file(
        self, km: KeyManager, keys_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        keys_path.write_text('FILE_KEY="val"\n')
        monkeypatch.delenv("FILE_KEY", raising=False)
        assert km.has_key("FILE_KEY") is True

    def test_false_when_absent(self, km: KeyManager, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ABSENT", raising=False)
        assert km.has_key("ABSENT") is False
