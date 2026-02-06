"""FastAPI application factory with Amplifier lifecycle management."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_catalogue.config import get_config
from agent_catalogue.services.embedder import EmbedderService
from agent_catalogue.session_manager import SessionManager
from agent_catalogue.storage.duckdb import DuckDBRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    config = get_config()

    # Initialize storage
    db_repo = DuckDBRepository(config.storage)

    # Initialize embedder (direct Azure OpenAI SDK - not Amplifier)
    embedder = EmbedderService(config.embeddings)

    # Initialize Amplifier session manager
    session_mgr = SessionManager(config)
    await session_mgr.startup(db_repo, embedder)

    # Store on app state for route access
    app.state.config = config
    app.state.db_repo = db_repo
    app.state.embedder = embedder
    app.state.session_mgr = session_mgr

    logger.info("Agent Catalogue started (Amplifier-powered)")
    yield

    # Shutdown
    await session_mgr.shutdown()
    logger.info("Agent Catalogue shut down")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Agent Catalogue",
        description="Catalogue, analyze, and discover AI agent definitions",
        version="0.2.0",
        lifespan=lifespan,
    )

    # Templates
    template_dir = Path(__file__).parent.parent / "web" / "templates"
    templates = Jinja2Templates(directory=str(template_dir))
    app.state.templates = templates

    # Static files
    static_dir = Path(__file__).parent.parent / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Register routes
    from agent_catalogue.api.routes import router

    app.include_router(router)

    return app
