"""Catalogue tools for Amplifier sessions.

Provides tools that allow LLM agents to interact with the agent catalogue
(search, retrieve, store, analyze agents).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_catalogue.tools.analysis import ComputeEmbeddingTool, GetCatalogueStatsTool
from agent_catalogue.tools.search import ListAgentsTool, SearchSimilarTool
from agent_catalogue.tools.storage import (
    GetAgentBySlugTool,
    GetAgentContentTool,
    GetAgentTool,
    StoreAgentTool,
)

if TYPE_CHECKING:
    from agent_catalogue.services.embedder import EmbedderService
    from agent_catalogue.storage.duckdb import DuckDBRepository


def create_catalogue_tools(db_repo: DuckDBRepository, embedder: EmbedderService) -> list:
    """Factory: create all catalogue tool instances with injected dependencies."""
    return [
        SearchSimilarTool(db_repo, embedder),
        ListAgentsTool(db_repo),
        GetAgentTool(db_repo),
        GetAgentBySlugTool(db_repo),
        GetAgentContentTool(db_repo),
        StoreAgentTool(db_repo, embedder),
        GetCatalogueStatsTool(db_repo),
        ComputeEmbeddingTool(embedder),
    ]


__all__ = [
    "ComputeEmbeddingTool",
    "GetAgentBySlugTool",
    "GetAgentContentTool",
    "GetAgentTool",
    "GetCatalogueStatsTool",
    "ListAgentsTool",
    "SearchSimilarTool",
    "StoreAgentTool",
    "create_catalogue_tools",
]
