"""Provider utilities for Agent Catalogue.

Provides dynamic provider discovery, configuration, and model listing
following amplifier-app-cli patterns. Loads provider modules at runtime
to query their self-declared config_fields and available models.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import logging
import os
import subprocess
import sys
from typing import Any

from rich.console import Console
from rich.prompt import Confirm, Prompt

from agent_catalogue.key_manager import KeyManager

logger = logging.getLogger(__name__)
console = Console()

# Known provider git sources for installation
KNOWN_PROVIDER_SOURCES: dict[str, str] = {
    "provider-anthropic": (
        "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main"
    ),
    "provider-openai": ("git+https://github.com/microsoft/amplifier-module-provider-openai@main"),
    "provider-azure-openai": (
        "git+https://github.com/microsoft/amplifier-module-provider-azure-openai@main"
    ),
}

# Fallback display names when provider info unavailable
_DISPLAY_NAMES: dict[str, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "azure-openai": "Azure OpenAI",
    "gemini": "Google Gemini",
    "ollama": "Ollama",
    "vllm": "vLLM",
}

# Env vars that indicate a provider is configured
PROVIDER_CREDENTIAL_VARS: dict[str, list[str]] = {
    "provider-anthropic": ["ANTHROPIC_API_KEY"],
    "provider-openai": ["OPENAI_API_KEY"],
    "provider-azure-openai": ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"],
}


def install_known_providers(verbose: bool = True) -> bool:
    """Install known provider modules via uv pip install.

    Downloads provider packages from git on first run, uses cache after.
    """
    installed_any = False
    for module_id, source in KNOWN_PROVIDER_SOURCES.items():
        try:
            # Check if already importable
            provider_name = module_id.replace("provider-", "")
            mod_name = f"amplifier_module_provider_{provider_name.replace('-', '_')}"
            importlib.import_module(mod_name)
            if verbose:
                console.print(f"  [dim]{module_id}: already installed[/dim]")
            continue
        except ImportError:
            pass

        if verbose:
            console.print(f"  Installing {module_id}...")
        try:
            result = subprocess.run(
                ["uv", "pip", "install", source, "--python", sys.executable],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                installed_any = True
                if verbose:
                    console.print(f"  [green]{module_id}: installed[/green]")
            else:
                if verbose:
                    console.print(f"  [yellow]{module_id}: install failed[/yellow]")
                logger.debug("Install stderr: %s", result.stderr)
        except Exception as e:
            if verbose:
                console.print(f"  [yellow]{module_id}: {e}[/yellow]")

    if installed_any:
        # Refresh Python's view of installed packages
        importlib.invalidate_caches()
        import site

        for site_dir in site.getsitepackages():
            site.addsitedir(site_dir)

    return installed_any


def _get_display_name(module_id: str) -> str:
    """Get display name for a provider."""
    name = module_id.replace("provider-", "")
    return _DISPLAY_NAMES.get(name, name.replace("-", " ").title())


def _load_provider_module(provider_id: str) -> Any:
    """Load a provider Python module."""
    if provider_id.startswith("provider-"):
        provider_id = provider_id[9:]
    mod_name = f"amplifier_module_provider_{provider_id.replace('-', '_')}"

    # Try entry points first
    try:
        eps = importlib.metadata.entry_points(group="amplifier.modules")
        full_id = f"provider-{provider_id}"
        for ep in eps:
            if ep.name == full_id:
                mount_fn = ep.load()
                return importlib.import_module(mount_fn.__module__.rsplit(".", 1)[0])
    except Exception:
        pass

    return importlib.import_module(mod_name)


def _find_provider_class(module: Any) -> type | None:
    """Find the Provider class in a module."""
    for name in dir(module):
        if name.endswith("Provider") and not name.startswith("_"):
            cls = getattr(module, name, None)
            if cls and isinstance(cls, type):
                return cls
    return None


def _try_instantiate(cls: type, collected_config: dict[str, Any] | None = None) -> Any:
    """Try to instantiate a provider class with various signatures."""
    collected_config = collected_config or {}

    # Resolve ${VAR} placeholders
    def resolve(val: Any) -> str:
        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
            return os.environ.get(val[2:-1], "")
        return str(val) if val else ""

    base_url = (
        resolve(collected_config.get("base_url") or collected_config.get("azure_endpoint"))
        or "http://placeholder"
    )
    api_key = resolve(collected_config.get("api_key")) or ""

    for attempt in [
        lambda: cls(api_key=api_key, config={}),
        lambda: cls(base_url=base_url, api_key=api_key, config={}),
        lambda: cls(base_url=base_url, config={}),
        lambda: cls(config={}),
        lambda: cls(),
    ]:
        try:
            return attempt()
        except (TypeError, ValueError, RuntimeError):
            continue
    return None


def get_provider_info(provider_id: str) -> dict[str, Any] | None:
    """Get provider metadata including config_fields."""
    try:
        module = _load_provider_module(provider_id)
        cls = _find_provider_class(module)
        if not cls:
            return None
        instance = _try_instantiate(cls)
        if not instance or not hasattr(instance, "get_info"):
            return None
        info = instance.get_info()
        return info.model_dump() if hasattr(info, "model_dump") else vars(info)
    except Exception as e:
        logger.debug("get_provider_info failed for %s: %s", provider_id, e)
        return None


def get_provider_models(
    provider_id: str, collected_config: dict[str, Any] | None = None
) -> list[Any]:
    """Get available models from a provider's list_models()."""
    try:
        module = _load_provider_module(provider_id)
        cls = _find_provider_class(module)
        if not cls:
            return []
        instance = _try_instantiate(cls, collected_config)
        if not instance or not hasattr(instance, "list_models"):
            return []
        fn = instance.list_models
        if asyncio.iscoroutinefunction(fn):
            return asyncio.run(fn())
        return fn()
    except Exception as e:
        logger.debug("get_provider_models failed for %s: %s", provider_id, e)
        return []


def list_available_providers() -> list[tuple[str, str, str]]:
    """Discover installed provider modules dynamically.

    Returns list of (module_id, display_name, description).
    """
    providers: dict[str, tuple[str, str, str]] = {}

    # Discover via entry points
    try:
        eps = importlib.metadata.entry_points(group="amplifier.modules")
        for ep in eps:
            if ep.name.startswith("provider-"):
                info = get_provider_info(ep.name)
                if info:
                    display = info.get("display_name", _get_display_name(ep.name))
                    desc = info.get("description", "")
                else:
                    display = _get_display_name(ep.name)
                    desc = ""
                providers[ep.name] = (ep.name, display, desc)
    except Exception:
        pass

    # Also try known sources that may be installed but without entry points
    for module_id in KNOWN_PROVIDER_SOURCES:
        if module_id not in providers:
            try:
                _load_provider_module(module_id)
                info = get_provider_info(module_id)
                display = (
                    info.get("display_name", _get_display_name(module_id))
                    if info
                    else _get_display_name(module_id)
                )
                providers[module_id] = (module_id, display, "")
            except Exception:
                pass

    return sorted(providers.values(), key=lambda p: p[1].lower())


def detect_provider_from_env() -> str | None:
    """Detect provider from environment variables."""
    for provider_id, env_vars in PROVIDER_CREDENTIAL_VARS.items():
        if not env_vars:
            continue
        if all(os.environ.get(var) for var in env_vars):
            return provider_id
    return None


def _resolve_config_value(value: Any) -> Any:
    """Resolve ${VAR} references to actual env values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1])
    return value


def _should_show_field(field: dict[str, Any], collected: dict[str, Any]) -> bool:
    """Check show_when conditions for a field."""
    show_when = field.get("show_when")
    if not show_when:
        return True
    for key, expected in show_when.items():
        actual = str(collected.get(key, "")).lower()
        expected_str = str(expected).lower()
        if expected_str.startswith("contains:"):
            if expected_str[9:] not in actual:
                return False
        elif expected_str.startswith("startswith:"):
            if not actual.startswith(expected_str[11:]):
                return False
        elif actual != expected_str:
            return False
    return True


def _prompt_for_field(
    field: dict[str, Any],
    key_mgr: KeyManager,
    collected: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> tuple[str, Any]:
    """Prompt user for a config field, following app-cli patterns."""
    field_id = field["id"]
    field_type = field.get("field_type", "text")
    prompt_text = field["prompt"]
    env_var = field.get("env_var")
    default = field.get("default")
    required = field.get("required", True)

    # Check existing values: env var > existing config
    existing_env = os.environ.get(env_var) if env_var else None
    existing_cfg = None
    if existing and field_type != "secret":
        raw = existing.get(field_id)
        if raw:
            existing_cfg = _resolve_config_value(raw)
    existing_value = existing_env or existing_cfg

    # Show field
    console.print()
    console.print(f"[bold]{field.get('display_name', field_id)}[/bold]")
    if existing_value:
        if field_type == "secret":
            console.print(
                "  [dim](Found in environment/keyring - will use if you don't configure)[/dim]"
            )
        else:
            console.print(f"  [dim](Found: {existing_value})[/dim]")

    # Boolean
    if field_type == "boolean":
        if existing_value:
            default_bool = str(existing_value).lower() in ("true", "1", "yes")
        else:
            default_bool = bool(default and str(default).lower() in ("true", "1", "yes"))
        value = Confirm.ask(prompt_text, default=default_bool)
        return field_id, str(value).lower()

    # Choice
    if field_type == "choice":
        choices = field.get("choices", [])
        if choices:
            console.print(f"{prompt_text}")
            for idx, choice in enumerate(choices, 1):
                console.print(f"  [{idx}] {choice}")
            effective = existing_value or default
            default_choice = "1"
            if effective and effective in choices:
                default_choice = str(choices.index(effective) + 1)
            choice_map = {str(i): c for i, c in enumerate(choices, 1)}
            selected = Prompt.ask("Choice", choices=list(choice_map.keys()), default=default_choice)
            return field_id, choice_map[selected]

    # Secret
    if field_type == "secret":
        suffix = " (press Enter to keep existing)" if existing_value else ""
        value = Prompt.ask(f"{prompt_text}{suffix}", password=True, default="")
        if value:
            if env_var:
                key_mgr.save_key(env_var, value)
                os.environ[env_var] = value
                console.print("[green]Saved[/green]")
            return field_id, f"${{{env_var}}}" if env_var else value
        if existing_value:
            console.print("[green]Using existing[/green]")
            return field_id, f"${{{env_var}}}" if env_var else existing_value
        if required:
            msg = f"{field.get('display_name', field_id)} is required"
            raise ValueError(msg)
        return field_id, None

    # Text (default)
    effective_default = existing_value or default or ""
    value = Prompt.ask(prompt_text, default=str(effective_default))
    if not value and required:
        msg = f"{field.get('display_name', field_id)} is required"
        raise ValueError(msg)
    if value and env_var:
        key_mgr.save_key(env_var, value)
        os.environ[env_var] = value
        console.print("[green]Saved[/green]")
        return field_id, f"${{{env_var}}}"
    return field_id, value if value else None


def prompt_model_selection(
    provider_id: str,
    default_model: str | None = None,
    collected_config: dict[str, Any] | None = None,
) -> str:
    """Prompt user to select a model from provider's available models."""
    models = get_provider_models(provider_id, collected_config)

    if not models:
        console.print("  [dim](No models discovered from server.)[/dim]")
        return Prompt.ask("Model name", default=default_model or "")

    model_ids = [m.id for m in models]
    default_in_list = bool(default_model and default_model in model_ids)

    model_map: dict[str, str] = {}
    for idx, m in enumerate(models, 1):
        model_map[str(idx)] = m.id
        caps = ""
        if hasattr(m, "capabilities") and m.capabilities:
            key_caps = [c for c in m.capabilities if c in ("fast", "thinking", "vision")]
            if key_caps:
                caps = f" ({', '.join(key_caps)})"
        console.print(f"  [{idx}] {m.display_name}{caps}")

    next_idx = len(models) + 1

    # If current model not in list, add "keep current" option
    if default_model and not default_in_list:
        model_map[str(next_idx)] = default_model
        console.print(f"  [{next_idx}] {default_model} [dim](current)[/dim]")
        next_idx += 1

    # Custom option
    model_map[str(next_idx)] = "__custom__"
    console.print(f"  [{next_idx}] custom")

    # Default choice
    default_choice: str | None = None
    if default_model:
        for idx_str, mid in model_map.items():
            if mid == default_model:
                default_choice = idx_str
                break

    if default_choice:
        choice = Prompt.ask("Choice", choices=list(model_map.keys()), default=default_choice)
    else:
        choice = Prompt.ask("Choice", choices=list(model_map.keys()))

    if model_map[choice] == "__custom__":
        return Prompt.ask("Model name", default=default_model or "")

    return model_map[choice]


def configure_provider(
    provider_id: str,
    key_mgr: KeyManager,
    existing_config: dict[str, Any] | None = None,
    non_interactive: bool = False,
) -> dict[str, Any] | None:
    """Configure a provider using its self-declared config_fields.

    3-phase flow:
    1. Pre-model fields (credentials, endpoints)
    2. Model selection via list_models()
    3. Post-model fields (model-dependent options)
    """
    # Strip prefix
    bare_id = provider_id.removeprefix("provider-")

    info = get_provider_info(provider_id)
    if not info:
        console.print(f"[red]Error: Could not load provider '{provider_id}'[/red]")
        return None

    display_name = info.get("display_name", bare_id)
    if not non_interactive:
        console.print(f"\n[bold]Configuring {display_name}[/bold]")

    collected: dict[str, Any] = {}
    config_fields = info.get("config_fields", [])
    pre_model = [f for f in config_fields if not f.get("requires_model", False)]
    post_model = [f for f in config_fields if f.get("requires_model", False)]

    # Phase 1: Pre-model fields
    for field in pre_model:
        fid = field["id"]
        if not _should_show_field(field, collected):
            continue
        if non_interactive:
            env_var = field.get("env_var")
            if env_var and os.environ.get(env_var):
                collected[fid] = f"${{{env_var}}}"
            elif existing_config and fid in existing_config:
                collected[fid] = existing_config[fid]
            elif field.get("default"):
                collected[fid] = field["default"]
            continue
        fid, value = _prompt_for_field(field, key_mgr, collected, existing_config)
        if value is not None:
            collected[fid] = value

    # Phase 2: Model selection
    if non_interactive:
        if existing_config and "default_model" in existing_config:
            collected["default_model"] = existing_config["default_model"]
    else:
        default_model = existing_config.get("default_model") if existing_config else None
        console.print()
        console.print("[bold]Default Model[/bold]")
        selected = prompt_model_selection(bare_id, default_model, collected)
        if selected:
            collected["default_model"] = selected

    # Phase 3: Post-model fields
    for field in post_model:
        fid = field["id"]
        if not _should_show_field(field, collected):
            continue
        if non_interactive:
            env_var = field.get("env_var")
            if env_var and os.environ.get(env_var):
                collected[fid] = f"${{{env_var}}}"
            elif existing_config and fid in existing_config:
                collected[fid] = existing_config[fid]
            elif field.get("default"):
                collected[fid] = field["default"]
            continue
        fid, value = _prompt_for_field(field, key_mgr, collected, existing_config)
        if value is not None:
            collected[fid] = value

    if not non_interactive:
        console.print(f"\n[green]{display_name} configured[/green]")

    return collected
