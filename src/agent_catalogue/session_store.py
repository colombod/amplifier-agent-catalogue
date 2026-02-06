"""Session persistence for the Agent Catalogue.

Stores session transcripts (JSONL) and metadata (JSON) following the same
patterns as amplifier-app-cli's SessionStore:
- Atomic writes with backup for crash safety
- transcript.jsonl: one message per line (user/assistant only, no system)
- metadata.json: session metadata (id, timestamps, turn count, status)
- Flat storage under ~/.agent-catalogue/sessions/<session-id>/
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_catalogue.paths import get_session_dir, get_sessions_dir

logger = logging.getLogger(__name__)


class SessionStore:
    """Persists session transcripts and metadata to disk.

    Storage layout:
        ~/.agent-catalogue/sessions/<session-id>/
            transcript.jsonl    # One message per line
            metadata.json       # Session metadata
    """

    @property
    def sessions_dir(self) -> Path:
        """Root directory for all sessions."""
        return get_sessions_dir()

    def session_dir(self, session_id: str) -> Path:
        """Directory for a specific session."""
        return get_session_dir(session_id)

    def save(
        self,
        session_id: str,
        transcript: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> None:
        """Save session transcript and metadata. Best-effort, never throws."""
        try:
            session_path = self.session_dir(session_id)
            session_path.mkdir(parents=True, exist_ok=True)

            # Write transcript as JSONL (one message per line)
            transcript_path = session_path / "transcript.jsonl"
            _write_with_backup(
                transcript_path,
                "\n".join(json.dumps(msg, default=str) for msg in transcript) + "\n",
            )

            # Write metadata as JSON
            metadata_path = session_path / "metadata.json"
            # Merge with existing metadata to preserve fields set by other writers
            existing = _load_json(metadata_path) or {}
            existing.update(metadata)
            existing["updated_at"] = datetime.now(UTC).isoformat()
            _write_with_backup(
                metadata_path,
                json.dumps(existing, indent=2, default=str) + "\n",
            )

            logger.debug("Saved session %s (%d messages)", session_id, len(transcript))
        except Exception:
            logger.debug("Failed to save session %s", session_id, exc_info=True)

    def load(self, session_id: str) -> dict[str, Any] | None:
        """Load session transcript and metadata. Returns None if not found."""
        session_path = self.session_dir(session_id)
        if not session_path.exists():
            return None

        transcript_path = session_path / "transcript.jsonl"
        metadata_path = session_path / "metadata.json"

        transcript = _load_jsonl(transcript_path) or []
        metadata = _load_json(metadata_path) or {}

        return {
            "session_id": session_id,
            "transcript": transcript,
            "metadata": metadata,
        }

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recent sessions with metadata. Newest first."""
        if not self.sessions_dir.exists():
            return []

        sessions = []
        for session_path in sorted(
            self.sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if not session_path.is_dir():
                continue
            metadata = _load_json(session_path / "metadata.json") or {}
            metadata["session_id"] = session_path.name
            sessions.append(metadata)
            if len(sessions) >= limit:
                break

        return sessions

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Remove sessions older than N days. Returns count of removed sessions."""
        if not self.sessions_dir.exists():
            return 0

        cutoff = datetime.now(UTC).timestamp() - (days * 86400)
        removed = 0

        for session_path in self.sessions_dir.iterdir():
            if not session_path.is_dir():
                continue
            try:
                if session_path.stat().st_mtime < cutoff:
                    shutil.rmtree(session_path)
                    removed += 1
            except Exception:
                continue

        if removed:
            logger.info("Cleaned up %d sessions older than %d days", removed, days)
        return removed


# -- Helpers -----------------------------------------------------------------


def _write_with_backup(path: Path, content: str) -> None:
    """Write content to file with backup for crash safety.

    1. Write to .tmp file
    2. If original exists, rename to .backup
    3. Rename .tmp to final path
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    backup_path = path.with_suffix(path.suffix + ".backup")

    try:
        tmp_path.write_text(content, encoding="utf-8")

        if path.exists():
            shutil.copy2(path, backup_path)

        shutil.move(str(tmp_path), str(path))
    except Exception:
        # Clean up tmp on failure
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON file with backup fallback."""
    for p in [path, path.with_suffix(path.suffix + ".backup")]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _load_jsonl(path: Path) -> list[dict[str, Any]] | None:
    """Load JSONL file with backup fallback."""
    for p in [path, path.with_suffix(path.suffix + ".backup")]:
        if p.exists():
            try:
                lines = p.read_text(encoding="utf-8").strip().splitlines()
                return [json.loads(line) for line in lines if line.strip()]
            except (json.JSONDecodeError, OSError):
                continue
    return None
