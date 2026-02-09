"""Agent CRUD routes.

Provides endpoints for managing agents in the catalogue:
listing, retrieving, deleting, and downloading agent definitions.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from agent_catalogue.models.agent import Agent, AgentSummary, AgentVersion

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/agents")
async def list_agents(
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
) -> list[AgentSummary]:
    """List all agents."""
    db_repo = request.app.state.db_repo
    return db_repo.list_agents(limit=limit, offset=offset, search=search)


@router.get("/api/agents/{agent_id}")
async def get_agent(request: Request, agent_id: UUID) -> Agent:
    """Get agent details."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/api/agents/{agent_id}/versions")
async def get_versions(request: Request, agent_id: UUID) -> list[AgentVersion]:
    """Get all versions of an agent."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return db_repo.get_versions(agent_id)


@router.delete("/api/agents/{agent_id}")
async def delete_agent(request: Request, agent_id: UUID) -> dict[str, str]:
    """Delete an agent and all its versions."""
    db_repo = request.app.state.db_repo
    if not db_repo.delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": str(agent_id)}


@router.get("/api/agents/{agent_id}/download")
async def download_agent(
    request: Request,
    agent_id: UUID,
    version: int | None = Query(
        default=None, description="Version number (latest if not specified)"
    ),
    format: str = Query(
        default="md", description="Format: 'md' for raw markdown, 'json' for metadata"
    ),
):
    """Download an agent's AGENTS.md file."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if version:
        agent_version = db_repo.get_version_by_number(agent_id, version)
    else:
        agent_version = db_repo.get_latest_version(agent_id)

    if not agent_version:
        raise HTTPException(status_code=404, detail="Version not found")

    if format == "json":
        data = {
            "agent": {
                "id": str(agent.id),
                "name": agent.name,
                "slug": agent.slug,
                "description": agent.description,
            },
            "version": {
                "number": agent_version.version_number,
                "created_at": (
                    agent_version.created_at.isoformat() if agent_version.created_at else None
                ),
                "content_hash": agent_version.content_hash,
            },
            "metadata": agent_version.metadata,
            "content": agent_version.raw_content,
        }
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{agent.slug}-v{agent_version.version_number}.json"'
                )
            },
        )

    # Raw markdown
    return Response(
        content=agent_version.raw_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{agent.slug}.md"'},
    )
