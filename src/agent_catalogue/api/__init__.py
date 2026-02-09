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
    # ABSOLUTE PATH for log file
    log_file = Path("/tmp/agent-catalogue-debug.log")

    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    # File handler - DEBUG level, everything goes here
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    )
    root_logger.addHandler(file_handler)

    # Console handler - INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    )
    root_logger.addHandler(console_handler)

    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    # FORCE FLUSH
    file_handler.flush()
    print(f"\n*** LOGGING TO: {log_file} ***\n", flush=True)
    logger.info("Application starting - log file: %s", log_file)

    config = get_config()

    # Initialize storage
    logger.info("Initializing DuckDB at %s", config.storage.db_path)
    db_repo = DuckDBRepository(config.storage)

    # Initialize embedder (direct Azure OpenAI SDK - not Amplifier)
    logger.info(
        "Initializing embedder (endpoint=%s, auth=%s)",
        config.embeddings.endpoint,
        config.embeddings.auth,
    )
    embedder = EmbedderService(config.embeddings)

    # Initialize Amplifier session manager
    logger.info("Starting Amplifier SessionManager...")
    session_mgr = SessionManager(config)
    await session_mgr.startup(db_repo, embedder)

    # Store on app state for route access
    app.state.config = config
    app.state.db_repo = db_repo
    app.state.embedder = embedder
    app.state.session_mgr = session_mgr

    logger.info("Agent Catalogue ready on %s:%s", config.server.host, config.server.port)
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

    # Register routes - organized by domain
    from agent_catalogue.api import (
        agents_routes,
        analysis_routes,
        comparison_routes,
        recipes_routes,
        search_routes,
        streaming_routes,
        web_routes,
    )

    # Web routes (no prefix) - must be first for path matching
    app.include_router(web_routes.router)

    # API domain routes
    app.include_router(agents_routes.router)
    app.include_router(analysis_routes.router)
    app.include_router(streaming_routes.router)
    app.include_router(search_routes.router)
    app.include_router(comparison_routes.router)
    app.include_router(recipes_routes.router)

    return app
