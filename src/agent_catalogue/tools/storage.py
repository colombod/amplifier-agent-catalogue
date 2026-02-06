"""Storage tools for the agent catalogue."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from amplifier_core.models import ToolResult

from agent_catalogue.models.agent import Agent, AgentVersion

if TYPE_CHECKING:
    from agent_catalogue.services.embedder import EmbedderService
    from agent_catalogue.storage.duckdb import DuckDBRepository

logger = logging.getLogger(__name__)


class GetAgentTool:
    """Get detailed information about an agent by ID."""

    def __init__(self, db_repo: DuckDBRepository) -> None:
        self._db = db_repo

    @property
    def name(self) -> str:
        return "get_agent"

    @property
    def description(self) -> str:
        return "Get detailed information about an agent by its unique ID."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique agent identifier (UUID)",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            agent_uuid = UUID(input["agent_id"])
        except ValueError:
            return ToolResult(
                success=False,
                error={"message": f"Invalid UUID: {input['agent_id']}"},
            )

        try:
            agent = self._db.get_agent(agent_uuid)
            if not agent:
                return ToolResult(
                    success=False,
                    error={"message": f"Agent not found: {input['agent_id']}"},
                )

            version = self._db.get_latest_version(agent_uuid)

            return ToolResult(
                output={
                    "id": str(agent.id),
                    "name": agent.name,
                    "slug": agent.slug,
                    "description": agent.description,
                    "current_version": version.version_number if version else None,
                    "version_count": len(self._db.get_versions(agent_uuid)),
                    "created_at": agent.created_at.isoformat(),
                    "updated_at": agent.updated_at.isoformat(),
                    "metadata": version.metadata if version else {},
                }
            )
        except Exception as e:
            logger.exception("get_agent failed")
            return ToolResult(success=False, error={"message": str(e)})


class GetAgentBySlugTool:
    """Get an agent by its URL-friendly slug."""

    def __init__(self, db_repo: DuckDBRepository) -> None:
        self._db = db_repo

    @property
    def name(self) -> str:
        return "get_agent_by_slug"

    @property
    def description(self) -> str:
        return "Get an agent by its URL-friendly slug name."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "URL-friendly slug of the agent",
                },
            },
            "required": ["slug"],
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            agent = self._db.get_agent_by_slug(input["slug"])
            if not agent:
                return ToolResult(
                    success=False,
                    error={"message": f"Agent not found: {input['slug']}"},
                )

            return ToolResult(
                output={
                    "id": str(agent.id),
                    "name": agent.name,
                    "slug": agent.slug,
                    "description": agent.description,
                    "created_at": agent.created_at.isoformat(),
                    "updated_at": agent.updated_at.isoformat(),
                }
            )
        except Exception as e:
            logger.exception("get_agent_by_slug failed")
            return ToolResult(success=False, error={"message": str(e)})


class GetAgentContentTool:
    """Get the raw AGENTS.md content for an agent."""

    def __init__(self, db_repo: DuckDBRepository) -> None:
        self._db = db_repo

    @property
    def name(self) -> str:
        return "get_agent_content"

    @property
    def description(self) -> str:
        return "Get the raw AGENTS.md content for an agent."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique agent identifier (UUID)",
                },
                "version": {
                    "type": "integer",
                    "description": "Version number (omit for latest)",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            agent_uuid = UUID(input["agent_id"])
        except ValueError:
            return ToolResult(
                success=False,
                error={"message": f"Invalid UUID: {input['agent_id']}"},
            )

        try:
            agent = self._db.get_agent(agent_uuid)
            if not agent:
                return ToolResult(
                    success=False,
                    error={"message": f"Agent not found: {input['agent_id']}"},
                )

            version_num = input.get("version")
            if version_num is not None:
                version = self._db.get_version_by_number(agent_uuid, version_num)
            else:
                version = self._db.get_latest_version(agent_uuid)

            if not version:
                return ToolResult(
                    success=False,
                    error={"message": "Version not found"},
                )

            return ToolResult(
                output={
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "version": version.version_number,
                    "content": version.raw_content,
                    "content_hash": version.content_hash,
                }
            )
        except Exception as e:
            logger.exception("get_agent_content failed for agent_id=%s", input.get("agent_id"))
            return ToolResult(
                success=False,
                error={"message": f"get_agent_content error: {type(e).__name__}: {e}"},
            )


class StoreAgentTool:
    """Store a new agent or new version in the catalogue."""

    def __init__(self, db_repo: DuckDBRepository, embedder: EmbedderService) -> None:
        self._db = db_repo
        self._embedder = embedder

    @property
    def name(self) -> str:
        return "store_agent"

    @property
    def description(self) -> str:
        return (
            "Store a new agent or new version in the catalogue. "
            "Requires metadata, raw content, and optionally evaluation results."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the agent",
                },
                "slug": {
                    "type": "string",
                    "description": "URL-friendly slug for the agent",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the agent",
                },
                "raw_content": {
                    "type": "string",
                    "description": "Full AGENTS.md markdown content",
                },
                "metadata": {
                    "type": "object",
                    "description": "Extracted agent metadata (domains, capabilities, tools, etc.)",
                },
                "evaluation": {
                    "type": "object",
                    "description": "Optional evaluation/quality results",
                },
            },
            "required": ["name", "slug", "description", "raw_content", "metadata"],
        }

    async def execute(self, input: dict) -> ToolResult:
        try:
            raw_content = input["raw_content"]
            slug = input["slug"]
            metadata = input["metadata"]

            # Merge evaluation into metadata if provided
            evaluation = input.get("evaluation")
            if evaluation:
                metadata = {**metadata, "evaluation": evaluation}

            # Compute embedding from raw content
            embedding = self._embedder.embed(raw_content)

            # Compute content hash for dedup
            content_hash = hashlib.sha256(raw_content.encode()).hexdigest()

            # Check if agent already exists by slug
            existing = self._db.get_agent_by_slug(slug)

            if existing:
                # Create new version for existing agent
                version = AgentVersion(
                    agent_id=existing.id,
                    version_number=0,  # Auto-assigned by create_version
                    raw_content=raw_content,
                    content_hash=content_hash,
                    embedding=embedding,
                    metadata=metadata,
                )
                version = self._db.create_version(version)

                return ToolResult(
                    output={
                        "action": "updated",
                        "agent_id": str(existing.id),
                        "agent_name": existing.name,
                        "version": version.version_number,
                    }
                )
            else:
                # Create new agent + first version
                agent = Agent(
                    name=input["name"],
                    slug=slug,
                    description=input["description"],
                )
                agent = self._db.create_agent(agent)

                version = AgentVersion(
                    agent_id=agent.id,
                    version_number=0,  # Auto-assigned by create_version
                    raw_content=raw_content,
                    content_hash=content_hash,
                    embedding=embedding,
                    metadata=metadata,
                )
                version = self._db.create_version(version)

                return ToolResult(
                    output={
                        "action": "created",
                        "agent_id": str(agent.id),
                        "agent_name": agent.name,
                        "slug": agent.slug,
                        "version": version.version_number,
                    }
                )
        except Exception as e:
            logger.exception("store_agent failed")
            return ToolResult(success=False, error={"message": str(e)})
