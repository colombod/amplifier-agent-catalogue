"""CLI for Agent Catalogue."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

if TYPE_CHECKING:
    from agent_catalogue.key_manager import KeyManager

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Agent Catalogue - Catalogue, analyze, and discover AI agent definitions."""
    if ctx.invoked_subcommand is None:
        # Default to serve
        ctx.invoke(serve)


@cli.command()
@click.option("--host", default=None, help="Server host")
@click.option("--port", default=None, type=int, help="Server port")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str | None, port: int | None, reload: bool) -> None:
    """Start the Agent Catalogue web server."""
    import uvicorn

    from agent_catalogue.config import get_config
    from agent_catalogue.settings import has_provider_configured

    config = get_config()

    if not has_provider_configured():
        console.print(
            "[yellow]No provider configured.[/yellow] Run [bold]agent-catalogue init[/bold] first."
        )
        sys.exit(1)

    final_host = host or config.server.host
    final_port = port or config.server.port

    console.print(f"Starting Agent Catalogue on [bold]http://{final_host}:{final_port}[/bold]")

    uvicorn.run(
        "agent_catalogue.api:create_app",
        factory=True,
        host=final_host,
        port=final_port,
        reload=reload or config.server.debug,
    )


@cli.command()
def config() -> None:
    """Show current configuration."""
    from agent_catalogue.config import get_config
    from agent_catalogue.paths import (
        get_global_settings_path,
        get_keys_path,
        get_local_settings_path,
        get_project_settings_path,
    )

    cfg = get_config()

    console.print(Panel("[bold]Agent Catalogue Configuration[/bold]"))
    console.print()

    # Settings file locations
    console.print("[bold]Settings files:[/bold]")
    for label, path in [
        ("Global", get_global_settings_path()),
        ("Project", get_project_settings_path()),
        ("Local", get_local_settings_path()),
    ]:
        exists = "[green]exists[/green]" if path.exists() else "[dim]not found[/dim]"
        console.print(f"  {label}: {path} ({exists})")

    keys_path = get_keys_path()
    exists = "[green]exists[/green]" if keys_path.exists() else "[dim]not found[/dim]"
    console.print(f"  Keys:  {keys_path} ({exists})")
    console.print()

    # Providers
    console.print("[bold]Providers:[/bold]")
    if cfg.providers:
        for p in cfg.providers:
            active = " [green](active)[/green]" if p.is_active else ""
            console.print(f"  {p.module} (priority={p.priority}){active}")
    else:
        console.print("  [yellow]None configured[/yellow]")
    console.print()

    # Embeddings
    console.print("[bold]Embeddings:[/bold]")
    console.print(f"  Endpoint:   {cfg.embeddings.endpoint or '[dim]not set[/dim]'}")
    console.print(f"  Deployment: {cfg.embeddings.deployment}")
    console.print(f"  Model:      {cfg.embeddings.model}")
    console.print(f"  Dimensions: {cfg.embeddings.dimensions}")
    console.print(f"  Auth:       {cfg.embeddings.auth}")
    console.print()

    # Storage & Server
    console.print("[bold]Storage:[/bold]")
    console.print(f"  Database: {cfg.storage.db_path}")
    console.print()
    console.print("[bold]Server:[/bold]")
    console.print(f"  {cfg.server.host}:{cfg.server.port} (debug={cfg.server.debug})")


@cli.command()
@click.option("--yes", "-y", is_flag=True, help="Non-interactive mode (use env vars)")
def init(yes: bool) -> None:
    """Set up Agent Catalogue configuration.

    Walks through provider selection, embedding configuration, and
    server settings. Saves to ~/.agent-catalogue/settings.yaml and
    API keys to ~/.agent-catalogue/keys.env.
    """
    from agent_catalogue.key_manager import KeyManager
    from agent_catalogue.paths import get_global_settings_path
    from agent_catalogue.settings import load_settings, save_settings

    console.print(
        Panel(
            "[bold]Agent Catalogue Setup[/bold]\n\n"
            "This wizard will configure:\n"
            "  1. LLM provider (for agent tasks)\n"
            "  2. Embedding provider (for vector search)\n"
            "  3. Server settings",
            title="Welcome",
        )
    )
    console.print()

    key_mgr = KeyManager()
    key_mgr.load_keys()

    # Start with current settings or defaults
    if get_global_settings_path().exists():
        settings = load_settings()
        console.print("[dim]Existing configuration found. Values shown as defaults.[/dim]\n")
    else:
        settings = {
            "providers": [],
            "embeddings": {},
            "storage": {},
            "server": {},
        }

    # ── Step 1: LLM Provider ──────────────────────────────────────

    console.print("[bold]Step 1: LLM Provider[/bold]")
    console.print("Choose the provider for agent tasks (extraction, evaluation, etc.)\n")

    providers_menu = {
        "1": ("provider-azure-openai", "Azure OpenAI"),
        "2": ("provider-anthropic", "Anthropic"),
        "3": ("provider-openai", "OpenAI"),
    }

    for num, (_, label) in providers_menu.items():
        console.print(f"  [{num}] {label}")
    console.print()

    if yes:
        # Auto-detect from env vars
        import os

        if os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_OPENAI_API_KEY"):
            choice = "1"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            choice = "2"
        elif os.environ.get("OPENAI_API_KEY"):
            choice = "3"
        else:
            choice = "1"
        console.print(f"[dim]Auto-detected: {providers_menu[choice][1]}[/dim]")
    else:
        choice = Prompt.ask("Select provider", choices=["1", "2", "3"], default="1")

    provider_module, provider_label = providers_menu[choice]
    provider_config: dict[str, Any] = {"priority": 1}

    if provider_module == "provider-azure-openai":
        provider_config = _configure_azure_openai(key_mgr, yes)
    elif provider_module == "provider-anthropic":
        provider_config = _configure_anthropic(key_mgr, yes)
    elif provider_module == "provider-openai":
        provider_config = _configure_openai(key_mgr, yes)

    provider_config["priority"] = 1
    settings["providers"] = [{"module": provider_module, "config": provider_config}]

    # Ask about fallback provider
    if not yes:
        console.print()
        add_fallback = Confirm.ask("Add a fallback provider?", default=False)
        if add_fallback:
            console.print()
            remaining = {k: v for k, v in providers_menu.items() if v[0] != provider_module}
            for num, (_, label) in remaining.items():
                console.print(f"  [{num}] {label}")
            console.print()
            fb_choice = Prompt.ask("Select fallback", choices=list(remaining.keys()))
            fb_module, _ = remaining[fb_choice]
            fb_config: dict[str, Any] = {}

            if fb_module == "provider-azure-openai":
                fb_config = _configure_azure_openai(key_mgr, yes)
            elif fb_module == "provider-anthropic":
                fb_config = _configure_anthropic(key_mgr, yes)
            elif fb_module == "provider-openai":
                fb_config = _configure_openai(key_mgr, yes)

            fb_config["priority"] = 2
            settings["providers"].append({"module": fb_module, "config": fb_config})

    console.print()

    # ── Step 2: Embeddings ────────────────────────────────────────

    console.print("[bold]Step 2: Embedding Configuration[/bold]")
    console.print("Configure the embedding model for vector search.\n")

    emb = settings.get("embeddings", {})

    if yes:
        import os

        emb_endpoint = os.environ.get(
            "AZURE_OPENAI_ENDPOINT",
            provider_config.get("azure_endpoint", ""),
        )
    else:
        default_endpoint = emb.get(
            "endpoint",
            provider_config.get("azure_endpoint", ""),
        )
        emb_endpoint = Prompt.ask(
            "Azure OpenAI endpoint for embeddings",
            default=default_endpoint or "",
        )

    if yes:
        emb_deployment = emb.get("deployment", "text-embedding-3-large")
        emb_model = emb.get("model", "text-embedding-3-large")
        emb_dims = emb.get("dimensions", 3072)
        emb_auth = "rbac" if not os.environ.get("AZURE_OPENAI_API_KEY") else "api_key"
    else:
        emb_deployment = Prompt.ask(
            "Embedding deployment name",
            default=emb.get("deployment", "text-embedding-3-large"),
        )
        emb_model = Prompt.ask(
            "Embedding model name",
            default=emb.get("model", "text-embedding-3-large"),
        )
        emb_dims = IntPrompt.ask(
            "Embedding dimensions",
            default=emb.get("dimensions", 3072),
        )
        emb_auth = Prompt.ask(
            "Embedding auth method",
            choices=["rbac", "api_key"],
            default=emb.get("auth", "rbac"),
        )

        if emb_auth == "api_key":
            emb_api_key = Prompt.ask("Azure OpenAI API key for embeddings", password=True)
            if emb_api_key:
                key_mgr.save_key("AZURE_OPENAI_EMBEDDING_API_KEY", emb_api_key)

    settings["embeddings"] = {
        "endpoint": emb_endpoint,
        "deployment": emb_deployment,
        "model": emb_model,
        "dimensions": emb_dims,
        "api_version": emb.get("api_version", "2024-12-01-preview"),
        "auth": emb_auth,
    }
    if emb_auth == "api_key":
        settings["embeddings"]["api_key"] = "${AZURE_OPENAI_EMBEDDING_API_KEY}"

    console.print()

    # ── Step 3: Server Settings ───────────────────────────────────

    console.print("[bold]Step 3: Server Settings[/bold]")

    srv = settings.get("server", {})
    if yes:
        settings["server"] = {
            "host": srv.get("host", "127.0.0.1"),
            "port": srv.get("port", 8000),
            "debug": srv.get("debug", False),
        }
    else:
        settings["server"] = {
            "host": Prompt.ask("Server host", default=srv.get("host", "127.0.0.1")),
            "port": int(Prompt.ask("Server port", default=str(srv.get("port", 8000)))),
            "debug": Confirm.ask("Enable debug mode?", default=srv.get("debug", False)),
        }

    # Storage
    settings["storage"] = {
        "db_path": str(settings.get("storage", {}).get("db_path", "./data/catalogue.duckdb")),
    }

    console.print()

    # ── Save ──────────────────────────────────────────────────────

    saved_path = save_settings(settings, scope="global")

    console.print(
        Panel(
            f"[green]Configuration saved![/green]\n\n"
            f"  Settings: {saved_path}\n"
            f"  Keys:     {key_mgr._path}\n\n"
            f"Start the server with: [bold]agent-catalogue serve[/bold]",
            title="Setup Complete",
        )
    )


# ── Provider Configuration Helpers ────────────────────────────────────


def _configure_azure_openai(key_mgr: KeyManager, non_interactive: bool) -> dict[str, Any]:
    """Configure Azure OpenAI provider."""
    import os

    if non_interactive:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        use_rbac = not api_key
        model = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")
    else:
        endpoint = Prompt.ask("Azure OpenAI endpoint")
        auth_choice = Prompt.ask(
            "Authentication method", choices=["rbac", "api_key"], default="rbac"
        )
        use_rbac = auth_choice == "rbac"
        if not use_rbac:
            api_key = Prompt.ask("Azure OpenAI API key", password=True)
            key_mgr.save_key("AZURE_OPENAI_API_KEY", api_key)
        else:
            api_key = ""
        model = Prompt.ask("Chat deployment name", default="gpt-4o")

    config: dict[str, Any] = {
        "azure_endpoint": endpoint,
        "default_model": model,
        "api_version": "2024-12-01-preview",
    }
    if use_rbac:
        config["use_default_credential"] = True
    else:
        config["api_key"] = "${AZURE_OPENAI_API_KEY}"

    return config


def _configure_anthropic(key_mgr: KeyManager, non_interactive: bool) -> dict[str, Any]:
    """Configure Anthropic provider."""
    import os

    if non_interactive:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        model = "claude-sonnet-4-20250514"
    else:
        api_key = Prompt.ask("Anthropic API key", password=True)
        model = Prompt.ask("Model name", default="claude-sonnet-4-20250514")

    if api_key:
        key_mgr.save_key("ANTHROPIC_API_KEY", api_key)

    return {
        "api_key": "${ANTHROPIC_API_KEY}",
        "default_model": model,
    }


def _configure_openai(key_mgr: KeyManager, non_interactive: bool) -> dict[str, Any]:
    """Configure OpenAI provider."""
    import os

    if non_interactive:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        model = "gpt-4o"
    else:
        api_key = Prompt.ask("OpenAI API key", password=True)
        model = Prompt.ask("Model name", default="gpt-4o")

    if api_key:
        key_mgr.save_key("OPENAI_API_KEY", api_key)

    return {
        "api_key": "${OPENAI_API_KEY}",
        "default_model": model,
    }


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
