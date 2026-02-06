"""Embedding generation service using Azure OpenAI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

if TYPE_CHECKING:
    from agent_catalogue.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class EmbedderService:
    """Generate vector embeddings using Azure OpenAI.

    Accepts the new EmbeddingConfig dataclass from settings.yaml.
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        """Initialize the embedder service.

        Args:
            config: Embedding configuration. Uses global config if not provided.
        """
        if config is None:
            from agent_catalogue.config import get_config

            config = get_config().embeddings
        self.config = config
        self._client: AzureOpenAI | None = None

    @property
    def client(self) -> AzureOpenAI:
        """Get or create the Azure OpenAI client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> AzureOpenAI:
        """Create Azure OpenAI client with appropriate authentication."""
        if self.config.auth == "api_key" and self.config.api_key:
            logger.info("Using API key authentication for embeddings")
            return AzureOpenAI(
                api_key=self.config.api_key,
                api_version=self.config.api_version,
                azure_endpoint=self.config.endpoint,
            )
        else:
            logger.info("Using RBAC authentication for embeddings")
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential,
                "https://cognitiveservices.azure.com/.default",
            )
            return AzureOpenAI(
                azure_ad_token_provider=token_provider,
                api_version=self.config.api_version,
                azure_endpoint=self.config.endpoint,
            )

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        response = self.client.embeddings.create(
            model=self.config.deployment,
            input=text,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.config.deployment,
            input=texts,
        )

        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    def similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        import math

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2, strict=True))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
