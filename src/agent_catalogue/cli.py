"""CLI for Agent Catalogue."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

if TYPE_CHECKING:
    pass

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Agent Catalogue - Catalogue, analyze, and discover AI agent definitions."""
    if ctx.invoked_subcommand is None:
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

    console.print("[bold]Providers:[/bold]")
    if cfg.providers:
        for p in cfg.providers:
            active = " [green](active)[/green]" if p.is_active else ""
            console.print(f"  {p.module} (priority={p.priority}){active}")
    else:
        console.print("  [yellow]None configured[/yellow]")
    console.print()

    console.print("[bold]Embeddings:[/bold]")
    console.print(f"  Endpoint:   {cfg.embeddings.endpoint or '[dim]not set[/dim]'}")
    console.print(f"  Deployment: {cfg.embeddings.deployment}")
    console.print(f"  Model:      {cfg.embeddings.model}")
    console.print(f"  Dimensions: {cfg.embeddings.dimensions}")
    console.print(f"  Auth:       {cfg.embeddings.auth}")
    console.print()

    console.print("[bold]Storage:[/bold]")
    console.print(f"  Database: {cfg.storage.db_path}")
    console.print()
    console.print("[bold]Server:[/bold]")
    console.print(f"  {cfg.server.host}:{cfg.server.port} (debug={cfg.server.debug})")


@cli.command()
@click.option("--yes", "-y", is_flag=True, help="Non-interactive mode (use env vars)")
def init(yes: bool) -> None:
    """Set up Agent Catalogue configuration.

    Dynamically discovers installed providers, prompts for configuration
    using each provider's self-declared config fields, and queries
    available models. Press Enter to keep existing values.
    """
    import importlib
    import site

    from agent_catalogue.key_manager import KeyManager
    from agent_catalogue.provider_utils import (
        configure_provider,
        detect_provider_from_env,
        install_known_providers,
        list_available_providers,
    )
    from agent_catalogue.settings import load_settings, save_settings

    # TTY check for interactive mode
    if not yes and not sys.stdin.isatty():
        console.print(
            "[red]Error:[/red] Interactive mode requires a TTY. "
            "Use --yes flag for non-interactive setup."
        )
        return

    key_mgr = KeyManager()
    key_mgr.load_keys()

    # Non-interactive mode
    if yes:
        settings = load_settings()
        module_id = detect_provider_from_env()
        if module_id is None:
            # Try keeping existing
            current = settings.get("providers", [])
            if current:
                module_id = current[0].get("module")
        if module_id is None:
            console.print("[red]Error:[/red] No provider credentials found in environment.")
            console.print(
                "\nSet one of: ANTHROPIC_API_KEY, OPENAI_API_KEY,"
                " AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT"
            )
            return

        install_known_providers(verbose=False)

        existing = None
        for p in settings.get("providers", []):
            if p.get("module") == module_id:
                existing = p.get("config", {})
                break

        provider_config = configure_provider(
            module_id, key_mgr, existing_config=existing, non_interactive=True
        )
        if provider_config is None:
            console.print("[red]Configuration failed.[/red]")
            return

        provider_config["priority"] = 1
        settings["providers"] = [{"module": module_id, "config": provider_config}]
        save_settings(settings, scope="global")

        display = module_id.removeprefix("provider-")
        console.print(f"[green]Configured {display} from environment[/green]")
        return

    # Interactive mode
    console.print()
    console.print(Panel.fit("[bold cyan]Agent Catalogue Setup[/bold cyan]", border_style="cyan"))
    console.print()

    # Step 0: Install providers
    console.print("[bold]Installing providers...[/bold]")
    install_known_providers(verbose=True)
    console.print()

    # Refresh import caches
    importlib.invalidate_caches()
    for site_dir in site.getsitepackages():
        site.addsitedir(site_dir)

    # Load existing settings
    settings = load_settings()
    current_providers = settings.get("providers", [])

    # Step 1: Provider selection (dynamic discovery)
    console.print("[bold]Step 1: Provider[/bold]")
    providers = list_available_providers()

    if not providers:
        console.print("[red]Error: No providers available. Installation may have failed.[/red]")
        return

    provider_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}
    for idx, (module_id, display, _desc) in enumerate(providers, 1):
        provider_map[str(idx)] = module_id
        reverse_map[module_id] = str(idx)
        console.print(f"  [{idx}] {display}")
    console.print()

    # Default to current provider
    default_choice = "1"
    if current_providers:
        current_module = current_providers[0].get("module", "")
        if current_module in reverse_map:
            default_choice = reverse_map[current_module]

    choice = Prompt.ask(
        "Which provider?", choices=list(provider_map.keys()), default=default_choice
    )
    module_id = provider_map[choice]

    # Get existing config for this provider
    existing_config: dict[str, Any] | None = None
    for p in current_providers:
        if p.get("module") == module_id:
            existing_config = p.get("config", {})
            break

    # Step 2: Provider-specific configuration (3-phase)
    provider_config = configure_provider(module_id, key_mgr, existing_config=existing_config)
    if provider_config is None:
        console.print("[red]Configuration cancelled.[/red]")
        return

    provider_config["priority"] = 1
    settings["providers"] = [{"module": module_id, "config": provider_config}]

    # Step 3: Embedding configuration
    console.print()
    console.print("[bold]Step 2: Embeddings[/bold]")
    console.print("Configure the embedding model for vector search.\n")

    emb = settings.get("embeddings", {})
    emb_endpoint = Prompt.ask(
        "Azure OpenAI endpoint for embeddings",
        default=emb.get("endpoint", provider_config.get("azure_endpoint", "")),
    )
    emb_deployment = Prompt.ask(
        "Embedding deployment name",
        default=emb.get("deployment", "text-embedding-3-large"),
    )
    emb_model = Prompt.ask(
        "Embedding model name",
        default=emb.get("model", emb_deployment),
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
        has_key = key_mgr.has_key("AZURE_OPENAI_EMBEDDING_API_KEY")
        if has_key:
            console.print("  [dim]Embedding API key: found in environment[/dim]")
            emb_key = Prompt.ask(
                "API key (press Enter to keep existing)", password=True, default=""
            )
        else:
            emb_key = Prompt.ask("Azure OpenAI API key for embeddings", password=True)
        if emb_key:
            key_mgr.save_key("AZURE_OPENAI_EMBEDDING_API_KEY", emb_key)

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

    # Step 4: Server settings
    console.print()
    console.print("[bold]Step 3: Server[/bold]")
    srv = settings.get("server", {})
    settings["server"] = {
        "host": Prompt.ask("Server host", default=srv.get("host", "127.0.0.1")),
        "port": int(Prompt.ask("Server port", default=str(srv.get("port", 8000)))),
        "debug": Confirm.ask("Enable debug mode?", default=srv.get("debug", False)),
    }
    settings["storage"] = {
        "db_path": str(settings.get("storage", {}).get("db_path", "./data/catalogue.duckdb")),
    }

    # Save
    console.print()
    save_settings(settings, scope="global")

    console.print(
        Panel.fit(
            "[bold green]Ready![/bold green]\n\n"
            "Start the server:\n"
            "  [cyan]agent-catalogue serve[/cyan]",
            border_style="green",
        )
    )
    console.print()


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
