"""Web UI routes.

Provides HTML page endpoints for the Agent Catalogue web interface.
All routes return rendered Jinja2 templates.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from agent_catalogue.models.agent import SearchResult

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with agent listing."""
    db_repo = request.app.state.db_repo
    templates = request.app.state.templates
    agents = db_repo.list_agents(limit=50)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "agents": agents, "count": db_repo.count_agents()},
    )


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Upload wizard page."""
    templates = request.app.state.templates
    return templates.TemplateResponse("upload.html", {"request": request})


@router.get("/agent/{slug}", response_class=HTMLResponse)
async def agent_detail(request: Request, slug: str):
    """Agent detail page."""
    db_repo = request.app.state.db_repo
    templates = request.app.state.templates

    agent = db_repo.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    versions = db_repo.get_versions(agent.id)
    current_version = db_repo.get_latest_version(agent.id)

    return templates.TemplateResponse(
        "agent_detail.html",
        {
            "request": request,
            "agent": agent,
            "versions": versions,
            "current_version": current_version,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query(default="", description="Search query"),
):
    """Search page."""
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    templates = request.app.state.templates

    results: list[SearchResult] = []
    if q:
        try:
            query_embedding = embedder.embed(q)
            results = db_repo.search(query_embedding, query_text=q, limit=20)
        except Exception as e:
            logger.error("Search error: %s", e)

    return templates.TemplateResponse(
        "search.html",
        {"request": request, "query": q, "results": results},
    )


@router.get("/download/{slug}")
async def download_by_slug(
    request: Request,
    slug: str,
    version: int | None = Query(default=None),
    format: str = Query(default="md"),
):
    """Download agent by slug (convenience route for web UI)."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # Import here to avoid circular import
    from agent_catalogue.api.agents_routes import download_agent

    return await download_agent(request, agent.id, version, format)


@router.post("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    file: Annotated[UploadFile, File()],
    force: bool = Form(default=False),
):
    """Handle form-based upload from web UI."""
    templates = request.app.state.templates
    try:
        # Import here to avoid circular import
        from agent_catalogue.api.analysis_routes import upload_agent

        result = await upload_agent(request, file, force)
        return RedirectResponse(
            url=f"/agent/{result.agent.slug}",
            status_code=303,
        )
    except HTTPException as e:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": e.detail},
            status_code=e.status_code,
        )
