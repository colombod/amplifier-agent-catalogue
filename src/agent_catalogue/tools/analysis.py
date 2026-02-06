"""Analysis and utility tools for the agent catalogue."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from amplifier_core.models import ToolResult

if TYPE_CHECKING:
    from agent_catalogue.services.embedder import EmbedderService
    from agent_catalogue.storage.duckdb import DuckDBRepository

logger = logging.getLogger(__name__)


class GetCatalogueStatsTool:
    """Get aggregate statistics about the agent catalogue."""

    def __init__(self, db_repo: DuckDBRepository) -> None:
        self._db = db_repo

    @property
    def name(self) -> str:
        return "get_catalogue_stats"

    @property
    def description(self) -> str:
        return (
            "Get aggregate statistics about the agent catalogue "
            "(total agents, domains, avg quality scores)."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            agents = self._db.list_agents(limit=1000)

            # Aggregate domain counts and version totals
            domains: dict[str, int] = {}
            total_versions = 0

            for agent in agents:
                total_versions += agent.current_version or 1

                for domain in agent.domains:
                    domains[domain] = domains.get(domain, 0) + 1

            return ToolResult(
                output={
                    "total_agents": len(agents),
                    "total_versions": total_versions,
                    "domains": dict(sorted(domains.items(), key=lambda x: -x[1])[:10]),
                }
            )
        except Exception as e:
            logger.exception("get_catalogue_stats failed")
            return ToolResult(success=False, error={"message": str(e)})


class ComputeEmbeddingTool:
    """Generate a vector embedding for text content."""

    def __init__(self, embedder: EmbedderService) -> None:
        self._embedder = embedder

    @property
    def name(self) -> str:
        return "compute_embedding"

    @property
    def description(self) -> str:
        return "Generate a vector embedding for text content. Useful for similarity comparisons."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text content to embed",
                },
            },
            "required": ["text"],
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            text = input["text"]
            embedding = self._embedder.embed(text)

            return ToolResult(
                output={
                    "text_length": len(text),
                    "embedding_dimensions": len(embedding),
                    "embedding": embedding,
                }
            )
        except Exception as e:
            logger.exception("compute_embedding failed")
            return ToolResult(success=False, error={"message": str(e)})
