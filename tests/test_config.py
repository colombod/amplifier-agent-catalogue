"""Tests for agent_catalogue.config module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_catalogue.config import (
    Config,
    EmbeddingConfig,
    ProviderConfig,
    ServerConfig,
    StorageConfig,
    reset_config,
)

# -- ProviderConfig ---------------------------------------------------------


class TestProviderConfig:
    def test_priority_defaults_to_10(self):
        p = ProviderConfig(module="provider-anthropic")
        assert p.priority == 10

    def test_priority_from_config(self):
        p = ProviderConfig(module="provider-anthropic", config={"priority": 5})
        assert p.priority == 5

    def test_is_active_true_when_priority_1(self):
        p = ProviderConfig(module="provider-anthropic", config={"priority": 1})
        assert p.is_active is True

    def test_is_active_false_when_priority_not_1(self):
        p = ProviderConfig(module="provider-anthropic", config={"priority": 2})
        assert p.is_active is False

    def test_is_active_false_by_default(self):
        p = ProviderConfig(module="provider-anthropic")
        assert p.is_active is False


# -- EmbeddingConfig --------------------------------------------------------


class TestEmbeddingConfig:
    def test_use_rbac_true_when_auth_rbac(self):
        e = EmbeddingConfig(auth="rbac")
        assert e.use_rbac is True

    def test_use_rbac_false_when_auth_api_key(self):
        e = EmbeddingConfig(auth="api_key")
        assert e.use_rbac is False

    def test_defaults(self):
        e = EmbeddingConfig()
        assert e.deployment == "text-embedding-3-large"
        assert e.model == "text-embedding-3-large"
        assert e.dimensions == 3072
        assert e.auth == "rbac"
        assert e.endpoint == ""


# -- ServerConfig -----------------------------------------------------------


class TestServerConfig:
    def test_defaults(self):
        s = ServerConfig()
        assert s.host == "127.0.0.1"
        assert s.port == 8000
        assert s.debug is False


# -- StorageConfig ----------------------------------------------------------


class TestStorageConfig:
    def test_default_db_path(self):
        s = StorageConfig()
        assert isinstance(s.db_path, Path)
        assert s.db_path.name == "catalogue.duckdb"


# -- Config -----------------------------------------------------------------


class TestConfigActiveProvider:
    def test_returns_none_when_no_providers(self):
        c = Config()
        assert c.active_provider is None

    def test_returns_lowest_priority(self):
        c = Config(
            providers=[
                ProviderConfig(module="high", config={"priority": 10}),
                ProviderConfig(module="low", config={"priority": 1}),
                ProviderConfig(module="mid", config={"priority": 5}),
            ]
        )
        assert c.active_provider is not None
        assert c.active_provider.module == "low"

    def test_returns_single_provider(self):
        c = Config(providers=[ProviderConfig(module="only", config={"priority": 3})])
        assert c.active_provider is not None
        assert c.active_provider.module == "only"


class TestConfigLoad:
    """Test Config.load() by mocking underlying dependencies."""

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Prevent Config.load() from reading real files."""
        # Reset the global singleton
        reset_config()

        # Mock KeyManager.load_keys to be a no-op
        monkeypatch.setattr(
            "agent_catalogue.config.KeyManager.load_keys",
            lambda self: None,
        )

        # Mock load_settings to return controlled data
        self._settings: dict[str, Any] = {
            "providers": [
                {
                    "module": "provider-anthropic",
                    "config": {"priority": 1, "api_key": "sk-test"},
                }
            ],
            "embeddings": {
                "endpoint": "https://embed.example.com",
                "deployment": "embed-v1",
                "model": "embed-v1",
                "dimensions": 1536,
                "api_version": "2024-01-01",
                "auth": "api_key",
                "api_key": "embed-key",
            },
            "storage": {"db_path": str(tmp_path / "test.duckdb")},
            "server": {"host": "0.0.0.0", "port": 3000, "debug": True},
        }
        monkeypatch.setattr(
            "agent_catalogue.config.load_settings",
            lambda: self._settings,
        )

    def test_load_produces_correct_types(self):
        cfg = Config.load()
        assert isinstance(cfg, Config)
        assert isinstance(cfg.providers, list)
        assert isinstance(cfg.embeddings, EmbeddingConfig)
        assert isinstance(cfg.storage, StorageConfig)
        assert isinstance(cfg.server, ServerConfig)

    def test_load_providers_parsed(self):
        cfg = Config.load()
        assert len(cfg.providers) == 1
        assert cfg.providers[0].module == "provider-anthropic"
        assert cfg.providers[0].priority == 1

    def test_load_embeddings_parsed(self):
        cfg = Config.load()
        assert cfg.embeddings.endpoint == "https://embed.example.com"
        assert cfg.embeddings.dimensions == 1536
        assert cfg.embeddings.auth == "api_key"
        assert cfg.embeddings.use_rbac is False

    def test_load_server_parsed(self):
        cfg = Config.load()
        assert cfg.server.host == "0.0.0.0"
        assert cfg.server.port == 3000
        assert cfg.server.debug is True

    def test_load_storage_parsed(self, tmp_path: Path):
        cfg = Config.load()
        assert cfg.storage.db_path == tmp_path / "test.duckdb"

    def test_load_raw_settings_preserved(self):
        cfg = Config.load()
        assert cfg.raw_settings["server"]["port"] == 3000

    def test_load_empty_providers(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "agent_catalogue.config.load_settings",
            lambda: {"providers": [], "embeddings": {}, "storage": {}, "server": {}},
        )
        cfg = Config.load()
        assert cfg.providers == []
        assert cfg.active_provider is None
