"""CLI entry point for the Agent Catalogue."""

from __future__ import annotations


def main() -> None:
    """Run the Agent Catalogue server."""
    import uvicorn

    from agent_catalogue.config import get_config

    config = get_config()
    uvicorn.run(
        "agent_catalogue.api:create_app",
        factory=True,
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
    )


if __name__ == "__main__":
    main()
