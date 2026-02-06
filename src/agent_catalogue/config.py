"""Configuration for Agent Catalogue.

Loads from settings.yaml (via the settings module) and provides
typed access to all configuration values. Also initializes the
KeyManager to populate env vars from keys.env before settings
are resolved.

Config flow:
  keys.env → os.environ → settings.yaml (${VAR} resolved) → Config
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_catalogue.key_manager import KeyManager
from agent_catalogue.paths import get_default_db_path
from agent_catalogue.settings import load_settings

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single Amplifier provider."""

    module: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def priority(self) -> int:
        return self.config.get("priority", 10)

    @property
    def is_active(self) -> bool:
        return self.priority == 1


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding service (direct Azure OpenAI SDK)."""

    endpoint: str = ""
    deployment: str = "text-embedding-3-large"
    model: str = "text-embedding-3-large"
    dimensions: int = 3072
    api_version: str = "2024-12-01-preview"
    auth: str = "rbac"  # "rbac" or "api_key"
    api_key: str = ""

    @property
    def use_rbac(self) -> bool:
        return self.auth == "rbac"


@dataclass
class StorageConfig:
    """Storage configuration."""

    db_path: Path = field(default_factory=get_default_db_path)


@dataclass
class ServerConfig:
    """Server configuration."""

    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False


@dataclass
class Config:
    """Main configuration combining all sub-configs.

    Built from settings.yaml + keys.env + env vars.
    """

    providers: list[ProviderConfig] = field(default_factory=list)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    raw_settings: dict[str, Any] = field(default_factory=dict)

    @property
    def active_provider(self) -> ProviderConfig | None:
        """Get the active (lowest priority) provider."""
        if not self.providers:
            return None
        return min(self.providers, key=lambda p: p.priority)

    @classmethod
    def load(cls) -> Config:
        """Load configuration from settings.yaml + keys.env + env vars.

        1. KeyManager loads keys.env into os.environ
        2. settings.yaml loaded and merged (global < project < local)
        3. ${VAR} placeholders resolved from os.environ
        4. Typed Config built from resolved settings
        """
        # Step 1: Load API keys into env
        key_mgr = KeyManager()
        key_mgr.load_keys()

        # Step 2+3: Load and resolve settings
        settings = load_settings()

        # Step 4: Build typed config
        providers = []
        for prov_dict in settings.get("providers", []):
            providers.append(
                ProviderConfig(
                    module=prov_dict.get("module", ""),
                    config=prov_dict.get("config", {}),
                )
            )

        emb = settings.get("embeddings", {})
        embeddings = EmbeddingConfig(
            endpoint=emb.get("endpoint", ""),
            deployment=emb.get("deployment", "text-embedding-3-large"),
            model=emb.get("model", "text-embedding-3-large"),
            dimensions=emb.get("dimensions", 3072),
            api_version=emb.get("api_version", "2024-12-01-preview"),
            auth=emb.get("auth", "rbac"),
            api_key=emb.get("api_key", ""),
        )

        stor = settings.get("storage", {})
        db_path_str = stor.get("db_path", "")
        storage = StorageConfig(
            db_path=Path(db_path_str).expanduser() if db_path_str else get_default_db_path(),
        )

        srv = settings.get("server", {})
        server = ServerConfig(
            host=srv.get("host", "127.0.0.1"),
            port=int(srv.get("port", 8000)),
            debug=bool(srv.get("debug", False)),
        )

        return cls(
            providers=providers,
            embeddings=embeddings,
            storage=storage,
            server=server,
            raw_settings=settings,
        )


# ── Global singleton ──────────────────────────────────────────────────

_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
