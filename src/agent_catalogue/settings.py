"""Settings management for Agent Catalogue.

Loads configuration from a layered settings.yaml system:
1. Global:  ~/.agent-catalogue/settings.yaml (user defaults)
2. Project: .agent-catalogue/settings.yaml   (team-shared, committed)
3. Local:   .agent-catalogue/settings.local.yaml (machine-specific, gitignored)

Higher layers override lower. ${VAR_NAME} placeholders in values
are resolved from environment variables (populated by KeyManager).
"""

from __future__ import annotations

import copy
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from agent_catalogue.paths import (
    get_global_settings_path,
    get_local_settings_path,
    get_project_settings_path,
)

logger = logging.getLogger(__name__)

ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

# Default settings (used when no settings.yaml exists)
DEFAULT_SETTINGS: dict[str, Any] = {
    "providers": [],
    "embeddings": {
        "endpoint": "",
        "deployment": "text-embedding-3-large",
        "model": "text-embedding-3-large",
        "dimensions": 3072,
        "api_version": "2024-12-01-preview",
        "auth": "rbac",
    },
    "storage": {
        "db_path": "./data/catalogue.duckdb",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "debug": False,
    },
}


def load_settings() -> dict[str, Any]:
    """Load and merge settings from all scopes.

    Merge order (last wins): defaults < global < project < local
    Then resolves ${VAR} placeholders from environment.
    """
    result = copy.deepcopy(DEFAULT_SETTINGS)

    # Layer 1: Global settings
    global_path = get_global_settings_path()
    if global_path.exists():
        global_settings = _load_yaml(global_path)
        if global_settings:
            _deep_merge(result, global_settings)

    # Layer 2: Project settings
    project_path = get_project_settings_path()
    if project_path.exists():
        project_settings = _load_yaml(project_path)
        if project_settings:
            _deep_merge(result, project_settings)

    # Layer 3: Local settings (gitignored overrides)
    local_path = get_local_settings_path()
    if local_path.exists():
        local_settings = _load_yaml(local_path)
        if local_settings:
            _deep_merge(result, local_settings)

    # Resolve ${VAR} and ${VAR:default} placeholders
    _resolve_env_vars(result)

    return result


def save_settings(settings: dict[str, Any], scope: str = "global") -> Path:
    """Save settings to the specified scope's settings.yaml.

    Args:
        settings: Settings dict to save.
        scope: "global", "project", or "local".

    Returns:
        Path to the saved settings file.
    """
    if scope == "global":
        path = get_global_settings_path()
    elif scope == "project":
        path = get_project_settings_path()
    elif scope == "local":
        path = get_local_settings_path()
    else:
        raise ValueError(f"Unknown scope: {scope}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(settings, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Saved settings to %s", path)
    return path


def has_settings() -> bool:
    """Check if any settings.yaml exists (used for first-run detection)."""
    return get_global_settings_path().exists() or get_project_settings_path().exists()


def has_provider_configured(settings: dict[str, Any] | None = None) -> bool:
    """Check if at least one provider is configured."""
    if settings is None:
        settings = load_settings()
    providers = settings.get("providers", [])
    return bool(providers)


# ── Internal Helpers ──────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load a YAML file, returning None on error."""
    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("Failed to load %s", path, exc_info=True)
        return None


def _deep_merge(base: dict, overlay: dict) -> None:
    """Recursively merge overlay into base. Overlay wins on conflicts."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


def _resolve_env_vars(data: Any) -> Any:
    """Recursively resolve ${VAR} and ${VAR:default} in string values."""
    if isinstance(data, dict):
        for key in data:
            data[key] = _resolve_env_vars(data[key])
    elif isinstance(data, list):
        for i, item in enumerate(data):
            data[i] = _resolve_env_vars(item)
    elif isinstance(data, str):

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            return os.environ.get(var_name, default or "")

        data = ENV_PATTERN.sub(replacer, data)
    return data
