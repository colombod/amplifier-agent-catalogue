"""Search and listing tools for the agent catalogue."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from amplifier_core.models import ToolResult

if TYPE_CHECKING:
    from agent_catalogue.services.embedder import EmbedderService
    from agent_catalogue.storage.duckdb import DuckDBRepository

logger = logging.getLogger(__name__)


class SearchSimilarTool:
    """Search the agent catalogue using vector similarity."""

    def __init__(self, db_repo: DuckDBRepository, embedder: EmbedderService) -> None:
        self._db = db_repo
        self._embedder = embedder

    @property
    def name(self) -> str:
        return "search_similar"

    @property
    def description(self) -> str:
        return (
            "Search the agent catalogue for agents similar to a text query "
            "using vector similarity. Returns ranked results with similarity scores."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for similar agents",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10, max 50)",
                    "default": 10,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            query = input["query"]
            limit = min(input.get("limit", 10), 50)

            embedding = self._embedder.embed(query)
            results = self._db.find_similar_with_metadata(
                embedding=embedding,
                threshold=0.3,
                limit=limit,
            )

            return ToolResult(
                output={
                    "count": len(results),
                    "agents": [
                        {
                            "id": str(summary.id),
                            "name": summary.name,
                            "slug": summary.slug,
                            "description": summary.description,
                            "similarity_score": round(score, 3),
                            "domains": metadata.get("domains", []),
                            "capabilities": metadata.get("capabilities", [])[:5],
                        }
                        for summary, score, metadata in results
                    ],
                }
            )
        except Exception as e:
            logger.exception("search_similar failed")
            return ToolResult(success=False, error={"message": str(e)})


class ListAgentsTool:
    """List agents in the catalogue with optional search."""

    def __init__(self, db_repo: DuckDBRepository) -> None:
        self._db = db_repo

    @property
    def name(self) -> str:
        return "list_agents"

    @property
    def description(self) -> str:
        return "List agents in the catalogue with optional text search filtering and pagination."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Optional text to filter agents by name or description",
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of agents to return",
                    "default": 20,
                },
            },
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            agents = self._db.list_agents(
                search=input.get("search"),
                offset=input.get("offset", 0),
                limit=input.get("limit", 20),
            )

            return ToolResult(
                output={
                    "count": len(agents),
                    "agents": [
                        {
                            "id": str(a.id),
                            "name": a.name,
                            "slug": a.slug,
                            "description": a.description,
                            "current_version": a.current_version,
                            "domains": a.domains,
                        }
                        for a in agents
                    ],
                }
            )
        except Exception as e:
            logger.exception("list_agents failed")
            return ToolResult(success=False, error={"message": str(e)})
