# Bundle Composition Pattern for Agent Catalogue

This document explains the critical bundle composition pattern used by the Agent Catalogue app to integrate with Amplifier.

## The Problem We Solved

The Agent Catalogue app needs to:
1. Create Amplifier sessions with custom providers (Anthropic, Azure OpenAI)
2. Access recipe execution capabilities (tool-recipes)
3. Mount custom catalogue tools (search, storage) with runtime dependencies
4. Use foundation's standard tools (filesystem, bash, web, delegate)

**Initial attempts failed** with errors like:
- `Module 'loop-basic' not found` (module resolver couldn't find orchestrator)
- `No providers mounted` (providers weren't being activated)
- `No module named 'anthropic'` (SDK dependencies missing)

## The Correct Pattern (4 Steps)

### Step 1: Install Provider Modules During Startup

**CRITICAL**: Provider modules must be installed with their SDK dependencies BEFORE bundle composition.

```python
async def _install_providers(self) -> None:
    """Install provider modules and their SDK dependencies."""
    # Well-known provider sources (from amplifier-app-cli)
    KNOWN_PROVIDER_SOURCES = {
        "provider-anthropic": "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main",
        "provider-openai": "git+https://github.com/microsoft/amplifier-module-provider-openai@main",
        "provider-azure-openai": "git+https://github.com/microsoft/amplifier-module-provider-azure-openai@main",
    }
    
    for provider_module in providers_to_install:
        source = KNOWN_PROVIDER_SOURCES[provider_module]
        # uv pip install downloads module AND installs its dependencies
        subprocess.run(
            ["uv", "pip", "install", "--python", sys.executable, source],
            check=True,
        )
```

**Why this is required:**
- `Bundle.prepare(install_deps=True)` only downloads provider MODULE code
- It does NOT install the provider's SDK dependencies (anthropic, openai packages)
- The CLI solves this with `install_known_providers()` during `amplifier init`
- Web apps need to do this during startup before bundle composition

### Step 2: Use Foundation as Base Bundle

**CRITICAL**: Use `foundation` as the base, not `@recipes`.

```python
# ✅ CORRECT - foundation is the application base
foundation_bundle = await load_bundle(
    "git+https://github.com/microsoft/amplifier-foundation@main"
)

# ❌ WRONG - @recipes is a capability bundle, not an app base
recipes_bundle = await load_bundle(
    "git+https://github.com/microsoft/amplifier-bundle-recipes@main"
)
```

**Why foundation, not @recipes:**
- Foundation provides: orchestrator, context, tools, provider activation
- @recipes provides: tool-recipes only (inherits everything else from foundation via includes)
- Using @recipes as base breaks provider mounting

### Step 3: Override Bundle with Dict Form Source URIs

**CRITICAL**: Use dict form for module configs, not strings.

```python
# ✅ CORRECT - dict form preserves source URIs
override = Bundle(
    providers=[
        {
            "module": "provider-anthropic",
            "source": "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main",
            "config": {...}
        }
    ],
    tools=[
        {
            "module": "tool-recipes",
            "source": "git+https://github.com/microsoft/amplifier-bundle-recipes@main#subdirectory=modules/tool-recipes",
        }
    ],
    session={
        "default_provider": "provider-anthropic",
        "orchestrator": {
            "module": "loop-basic",
            "source": "git+https://github.com/microsoft/amplifier-module-loop-basic@main",
        },
        "context": {
            "module": "context-simple",
            "source": "git+https://github.com/microsoft/amplifier-module-context-simple@main",
        },
    },
)

# ❌ WRONG - string form wipes out source URIs
override = Bundle(
    session={
        "orchestrator": "loop-basic",  # No source URI!
        "context": "context-simple",    # No source URI!
    }
)
```

**Why this matters:**
- `Bundle.compose()` uses `deep_merge` on the session dict
- When merging `dict` vs `string`, the string WINS and replaces the entire dict
- Foundation's source URIs get wiped out
- The module resolver can't find modules without source URIs

### Step 4: Mount Custom Tools After Session Creation

For Python tool objects with runtime dependencies (DB connections, etc.):

```python
# 1. Create session from prepared bundle
session = await prepared_bundle.create_session(session_id=...)

# 2. Mount custom tools that need runtime dependencies
tools = create_catalogue_tools(db_repo, embedder)
for tool in tools:
    await session.coordinator.mount("tools", tool, name=tool.name)
```

**Why this pattern:**
- Custom tools have injected dependencies (db_repo, embedder)
- These can't be declared in YAML (they're runtime Python objects)
- The coordinator accepts post-creation mounts
- This is mechanism (mount points), not policy (what to mount)

## Complete Flow

```python
class SessionManager:
    async def startup(self):
        # 1. Install provider modules + SDK dependencies
        await self._install_providers()
        
        # 2. Load foundation bundle
        foundation = await load_bundle("git+https://github.com/microsoft/amplifier-foundation@main")
        
        # 3. Create override with providers, tools, config (dict form!)
        override = self._create_override_bundle()
        
        # 4. Compose foundation + override
        composed = foundation.compose(override)
        
        # 5. Prepare (download/install remaining modules)
        prepared = await composed.prepare(install_deps=True)
        
        # 6. Cache for reuse
        self._prepared_bundles["recipes"] = prepared
    
    async def create_session(self):
        # 7. Create session from prepared bundle
        prepared = await self._get_recipes_bundle()
        session = await prepared.create_session(session_id=...)
        
        # 8. Mount custom tools
        await self._mount_catalogue_tools(session)
        
        return session
```

## What We Learned (Session 8929d751 Analysis)

The previous debugging session spent 40 turns and 17 hours chasing these issues:
- Tried cache clearing, venv recreation, dependency reinstalls
- All failed because the root causes were architectural, not environmental

**The actual root causes:**
1. Missing provider SDK installation step
2. Using @recipes as base instead of foundation
3. String overrides destroying source URIs
4. Spawn callbacks missing catalogue tool mounts

**The fix:** Follow the amplifier-app-cli and amplifier-app-server pattern exactly.

## Key Takeaways

1. **Provider SDKs must be installed separately** - `Bundle.prepare()` is not enough
2. **Foundation is the app base** - capability bundles like @recipes are add-ons
3. **Always use dict form with source URIs** - string form breaks module resolution
4. **Custom tools mount post-creation** - standard pattern for runtime dependencies

## References

- amplifier-app-cli: `install_known_providers()` in init flow
- amplifier-app-server: Provider installation in `_create_amplifier_session()`
- Bundle composition: `amplifier-foundation/bundle.py` lines 98-213
- Module resolution: `amplifier-foundation/modules/resolver.py`
