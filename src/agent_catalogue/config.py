"""Configuration management for Agent Catalogue.

Supports:
- Azure OpenAI with API key or RBAC authentication for embeddings
- Standard OpenAI API for chat/extraction
- Anthropic API for chat/extraction
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAIConfig(BaseSettings):
    """Standard OpenAI API configuration for chat/extraction."""

    model_config = SettingsConfigDict(
        env_prefix="AS_OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str | None = Field(
        default=None,
        description="OpenAI API key",
    )
    base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API base URL",
    )
    model: str = Field(
        default="gpt-4o",
        description="Model name for chat/extraction",
    )


class AzureOpenAIConfig(BaseSettings):
    """Azure OpenAI configuration for embeddings."""

    model_config = SettingsConfigDict(
        env_prefix="AS_AZURE_OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Endpoint configuration
    endpoint: str = Field(
        default="",
        description="Azure OpenAI endpoint URL",
        examples=["https://your-resource.openai.azure.com/"],
    )
    api_version: str = Field(
        default="2024-02-01",
        description="Azure OpenAI API version",
    )

    # Deployment names
    chat_deployment: str = Field(
        default="gpt-4o",
        description="Deployment name for chat/completion model",
    )
    embedding_deployment: str = Field(
        default="text-embedding-3-small",
        description="Deployment name for embedding model",
    )

    # Authentication
    api_key: str | None = Field(
        default=None,
        description="Azure OpenAI API key. If not set, uses DefaultAzureCredential (RBAC)",
    )
    use_rbac: bool = Field(
        default=False,
        description="Use RBAC via DefaultAzureCredential instead of API key",
    )

    @property
    def auth_type(self) -> Literal["api_key", "rbac"]:
        """Return the authentication type being used."""
        if self.use_rbac or not self.api_key:
            return "rbac"
        return "api_key"


class AnthropicConfig(BaseSettings):
    """Anthropic API configuration for chat/extraction."""

    model_config = SettingsConfigDict(
        env_prefix="AS_ANTHROPIC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str | None = Field(
        default=None,
        description="Anthropic API key",
    )
    default_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Default Anthropic model for chat/extraction",
    )


class StorageConfig(BaseSettings):
    """Storage configuration."""

    model_config = SettingsConfigDict(
        env_prefix="AS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(
        default=Path.home() / ".agent-catalogue" / "catalogue.duckdb",
        description="Path to DuckDB database file",
    )

    @field_validator("db_path", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        """Expand ~ in path."""
        if isinstance(v, str):
            v = Path(v)
        return v.expanduser()


class ServerConfig(BaseSettings):
    """Server configuration."""

    model_config = SettingsConfigDict(
        env_prefix="AS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")


class Config(BaseSettings):
    """Main configuration combining all sub-configs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    azure_openai: AzureOpenAIConfig = Field(default_factory=AzureOpenAIConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment and .env file."""
        return cls(
            openai=OpenAIConfig(),
            azure_openai=AzureOpenAIConfig(),
            anthropic=AnthropicConfig(),
            storage=StorageConfig(),
            server=ServerConfig(),
        )


# Global config instance (lazy loaded)
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
