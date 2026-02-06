"""Path management for Agent Catalogue.

All file system paths are defined here. The app uses:
- ~/.agent-catalogue/           Global user data (settings, keys, cache, sessions)
- .agent-catalogue/             Project-local settings
"""

from __future__ import annotations

from pathlib import Path

# ── Root Directories ──────────────────────────────────────────────────

APP_NAME = "agent-catalogue"


def get_global_dir() -> Path:
    """Global data directory: ~/.agent-catalogue/"""
    return Path.home() / f".{APP_NAME}"


def get_project_dir() -> Path:
    """Project-local config directory: .agent-catalogue/ in CWD."""
    return Path.cwd() / f".{APP_NAME}"


# ── Settings Files ────────────────────────────────────────────────────


def get_global_settings_path() -> Path:
    """Global settings: ~/.agent-catalogue/settings.yaml"""
    return get_global_dir() / "settings.yaml"


def get_project_settings_path() -> Path:
    """Project settings: .agent-catalogue/settings.yaml (committed)"""
    return get_project_dir() / "settings.yaml"


def get_local_settings_path() -> Path:
    """Local settings: .agent-catalogue/settings.local.yaml (gitignored)"""
    return get_project_dir() / "settings.local.yaml"


# ── Keys ──────────────────────────────────────────────────────────────


def get_keys_path() -> Path:
    """API keys file: ~/.agent-catalogue/keys.env (chmod 600)"""
    return get_global_dir() / "keys.env"


# ── Cache ─────────────────────────────────────────────────────────────


def get_cache_dir() -> Path:
    """Module cache: ~/.agent-catalogue/cache/"""
    return get_global_dir() / "cache"


# ── Sessions ──────────────────────────────────────────────────────────


def get_sessions_dir() -> Path:
    """Session transcripts: ~/.agent-catalogue/sessions/"""
    return get_global_dir() / "sessions"


def get_session_dir(session_id: str) -> Path:
    """Directory for a specific session."""
    safe_id = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    return get_sessions_dir() / safe_id


# ── Data ──────────────────────────────────────────────────────────────


def get_default_db_path() -> Path:
    """Default database path: ./data/catalogue.duckdb"""
    return Path.cwd() / "data" / "catalogue.duckdb"


# ── Agents & Context ──────────────────────────────────────────────────


def get_agents_dir() -> Path:
    """Agent definitions directory."""
    return Path(__file__).parent.parent.parent / "agents"


def get_context_dir() -> Path:
    """Context/knowledge files directory."""
    return Path(__file__).parent.parent.parent / "context"
