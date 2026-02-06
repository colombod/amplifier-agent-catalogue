"""Tests for agent_catalogue.cli module (no real server, no network)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from agent_catalogue.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestHelpText:
    def test_root_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Agent Catalogue" in result.output

    def test_serve_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--reload" in result.output

    def test_config_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "configuration" in result.output.lower()

    def test_init_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "--yes" in result.output


class TestConfigCommand:
    def test_config_runs_without_error(self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
        """The 'config' command should print config info (with mocked get_config)."""
        from agent_catalogue.config import Config, EmbeddingConfig, ServerConfig, StorageConfig

        fake_cfg = Config(
            providers=[],
            embeddings=EmbeddingConfig(),
            storage=StorageConfig(),
            server=ServerConfig(),
        )
        monkeypatch.setattr("agent_catalogue.cli.get_config", lambda: fake_cfg, raising=False)
        # The config command imports get_config at call time, so we also patch the module
        monkeypatch.setattr("agent_catalogue.config._config", fake_cfg)
        monkeypatch.setattr(
            "agent_catalogue.config.get_config",
            lambda: fake_cfg,
        )

        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "Configuration" in result.output or "configuration" in result.output.lower()
