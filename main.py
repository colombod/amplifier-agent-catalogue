"""Agent Catalogue - Entry point."""

import uvicorn

from agent_catalogue.api.routes import create_app
from agent_catalogue.config import get_config


def main():
    """Run the Agent Catalogue web application."""
    config = get_config()

    print("=" * 60)
    print("Agent Catalogue")
    print("=" * 60)
    print(f"Azure OpenAI Endpoint: {config.azure_openai.endpoint}")
    print(f"Auth Type: {config.azure_openai.auth_type}")
    print(f"Chat Deployment: {config.azure_openai.chat_deployment}")
    print(f"Embedding Deployment: {config.azure_openai.embedding_deployment}")
    print(f"Database: {config.storage.db_path}")
    print("=" * 60)

    app = create_app()

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
    )


if __name__ == "__main__":
    main()