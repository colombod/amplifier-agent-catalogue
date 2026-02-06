"""Tests for agent_catalogue.session_store module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from agent_catalogue.session_store import SessionStore, _load_json, _load_jsonl


@pytest.fixture()
def sessions_dir(tmp_path: Path) -> Path:
    """Root sessions directory inside tmp_path."""
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch, sessions_dir: Path) -> SessionStore:
    """SessionStore wired to tmp_path so nothing touches ~/.agent-catalogue."""
    monkeypatch.setattr(
        "agent_catalogue.session_store.get_sessions_dir",
        lambda: sessions_dir,
    )
    monkeypatch.setattr(
        "agent_catalogue.session_store.get_session_dir",
        lambda sid: sessions_dir / sid.replace("/", "_").replace("\\", "_").replace("..", "_"),
    )
    return SessionStore()


def _sample_transcript() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]


def _sample_metadata() -> dict[str, Any]:
    return {"session_id": "s1", "status": "active", "turns": 1}


# -- save -------------------------------------------------------------------


class TestSave:
    def test_creates_transcript_and_metadata(self, store: SessionStore, sessions_dir: Path):
        store.save("s1", _sample_transcript(), _sample_metadata())
        session_path = sessions_dir / "s1"
        assert (session_path / "transcript.jsonl").exists()
        assert (session_path / "metadata.json").exists()

    def test_transcript_is_valid_jsonl(self, store: SessionStore, sessions_dir: Path):
        store.save("s1", _sample_transcript(), _sample_metadata())
        lines = (sessions_dir / "s1" / "transcript.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            msg = json.loads(line)
            assert "role" in msg

    def test_metadata_is_valid_json(self, store: SessionStore, sessions_dir: Path):
        store.save("s1", _sample_transcript(), _sample_metadata())
        meta = json.loads((sessions_dir / "s1" / "metadata.json").read_text())
        assert meta["status"] == "active"
        assert "updated_at" in meta

    def test_metadata_merges_with_existing(self, store: SessionStore, sessions_dir: Path):
        store.save("s1", _sample_transcript(), {"extra": "field1"})
        store.save("s1", _sample_transcript(), {"status": "done"})
        meta = json.loads((sessions_dir / "s1" / "metadata.json").read_text())
        assert meta["extra"] == "field1"
        assert meta["status"] == "done"


# -- load -------------------------------------------------------------------


class TestLoad:
    def test_returns_saved_data(self, store: SessionStore):
        store.save("s1", _sample_transcript(), _sample_metadata())
        result = store.load("s1")
        assert result is not None
        assert result["session_id"] == "s1"
        assert len(result["transcript"]) == 2
        assert result["transcript"][0]["role"] == "user"

    def test_returns_none_for_nonexistent(self, store: SessionStore):
        assert store.load("does-not-exist") is None

    def test_metadata_includes_saved_fields(self, store: SessionStore):
        store.save("s1", _sample_transcript(), {"custom": "value"})
        result = store.load("s1")
        assert result is not None
        assert result["metadata"]["custom"] == "value"


# -- backup fallback --------------------------------------------------------


class TestBackupFallback:
    def test_backup_created_on_second_save(self, store: SessionStore, sessions_dir: Path):
        store.save("s1", _sample_transcript(), _sample_metadata())
        store.save("s1", _sample_transcript(), {"status": "updated"})
        backup = sessions_dir / "s1" / "metadata.json.backup"
        assert backup.exists()

    def test_transcript_backup_created(self, store: SessionStore, sessions_dir: Path):
        store.save("s1", _sample_transcript(), _sample_metadata())
        store.save("s1", _sample_transcript(), _sample_metadata())
        backup = sessions_dir / "s1" / "transcript.jsonl.backup"
        assert backup.exists()

    def test_corrupt_primary_falls_back_to_backup(self, sessions_dir: Path):
        """_load_json falls back to .backup when primary is corrupt."""
        primary = sessions_dir / "test.json"
        backup = sessions_dir / "test.json.backup"
        primary.write_text("NOT VALID JSON!!!")
        backup.write_text(json.dumps({"fallback": True}))
        result = _load_json(primary)
        assert result is not None
        assert result["fallback"] is True

    def test_corrupt_jsonl_falls_back_to_backup(self, sessions_dir: Path):
        """_load_jsonl falls back to .backup when primary is corrupt."""
        primary = sessions_dir / "test.jsonl"
        backup = sessions_dir / "test.jsonl.backup"
        primary.write_text("NOT VALID\n")
        backup.write_text(json.dumps({"role": "user"}) + "\n")
        result = _load_jsonl(primary)
        assert result is not None
        assert len(result) == 1
        assert result[0]["role"] == "user"


# -- list_sessions ----------------------------------------------------------


class TestListSessions:
    def test_returns_empty_when_no_sessions(self, store: SessionStore):
        assert store.list_sessions() == []

    def test_returns_sessions_newest_first(self, store: SessionStore, sessions_dir: Path):
        # Create sessions with staggered mtime
        store.save("older", _sample_transcript(), {"name": "older"})
        # Ensure distinct mtime by touching with a later timestamp
        time.sleep(0.05)
        store.save("newer", _sample_transcript(), {"name": "newer"})

        sessions = store.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "newer"
        assert sessions[1]["session_id"] == "older"

    def test_respects_limit(self, store: SessionStore):
        for i in range(5):
            store.save(f"s{i}", _sample_transcript(), {"i": i})
            time.sleep(0.02)
        sessions = store.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_skips_non_directory_entries(self, store: SessionStore, sessions_dir: Path):
        store.save("real", _sample_transcript(), _sample_metadata())
        (sessions_dir / "stray_file.txt").write_text("not a session")
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "real"


# -- cleanup_old_sessions ---------------------------------------------------


class TestCleanupOldSessions:
    def test_removes_old_sessions(self, store: SessionStore, sessions_dir: Path):
        store.save("old", _sample_transcript(), _sample_metadata())
        old_dir = sessions_dir / "old"
        # Backdate mtime to 60 days ago
        ancient = time.time() - (60 * 86400)
        for f in old_dir.rglob("*"):
            if f.is_file():
                import os

                os.utime(f, (ancient, ancient))
        os.utime(old_dir, (ancient, ancient))

        removed = store.cleanup_old_sessions(days=30)
        assert removed == 1
        assert not old_dir.exists()

    def test_keeps_recent_sessions(self, store: SessionStore, sessions_dir: Path):
        store.save("recent", _sample_transcript(), _sample_metadata())
        removed = store.cleanup_old_sessions(days=30)
        assert removed == 0
        assert (sessions_dir / "recent").exists()

    def test_returns_zero_when_no_sessions_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(
            "agent_catalogue.session_store.get_sessions_dir",
            lambda: tmp_path / "nonexistent",
        )
        s = SessionStore()
        assert s.cleanup_old_sessions(days=1) == 0
