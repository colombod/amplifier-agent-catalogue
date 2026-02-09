"""SessionManager: core Amplifier integration for the Agent Catalogue web app.

Manages Amplifier session lifecycle using bundle composition:
- Loads @recipes bundle for recipe execution capabilities
- Composes with custom Azure/Anthropic providers from app config
- Creates isolated sessions per recipe execution
- Mounts catalogue tools for agent operations
- Persists session transcripts and metadata for observability
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from amplifier_core import AmplifierSession
from amplifier_foundation import Bundle, load_bundle

from agent_catalogue.config import Config
from agent_catalogue.paths import get_agents_dir, get_cache_dir, get_context_dir
from agent_catalogue.session_store import SessionStore
from agent_catalogue.sse_bridge import SSEBridge
from agent_catalogue.tools import create_catalogue_tools

logger = logging.getLogger(__name__)

# Map agent names to their skill/knowledge file dependencies
AGENT_SKILLS: dict[str, list[str]] = {
    "extractor": ["agent-anatomy.md", "behavior-patterns.md"],
    "classifier": ["domain-taxonomy.md", "behavior-patterns.md"],
    "comparator": ["comparison-methodology.md", "behavior-patterns.md"],
    "narrator": ["quality-criteria.md", "comparison-methodology.md"],
    "evaluator": ["quality-criteria.md", "agent-anatomy.md"],
    "improver": ["quality-criteria.md", "agent-anatomy.md", "behavior-patterns.md"],
    "differentiator": ["agent-anatomy.md", "behavior-patterns.md", "domain-taxonomy.md"],
    "discovery": ["domain-taxonomy.md", "agent-anatomy.md"],
    "relevance": ["domain-taxonomy.md", "behavior-patterns.md"],
}


class SessionManager:
    """Manages Amplifier sessions using bundle composition pattern.

    Pattern from amplifier-app-server:
    1. Load @recipes bundle (includes foundation + tool-recipes)
    2. Create override Bundle with custom providers/session config
    3. Compose: recipes_bundle.compose(override)
    4. Prepare once (cached), create new session per execution

    This gives us:
    - tool-recipes for recipe execution
    - All foundation tools (filesystem, bash, web, delegate)
    - Custom Azure/Anthropic providers from app config
    - recipe-author and result-validator agents
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._db_repo: Any = None
        self._embedder: Any = None
        self._active_sessions: dict[str, AmplifierSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._hook_unregisters: dict[str, list] = {}
        self.sse_bridge = SSEBridge()
        self.session_store = SessionStore()
        self._agents_dir = get_agents_dir()
        self._context_dir = get_context_dir()
        self._cache_dir = get_cache_dir()
        self._agent_cache: dict[str, str] = {}

        # Cached prepared bundles (expensive to prepare)
        self._prepared_bundles: dict[str, Any] = {}

    async def startup(self, db_repo: Any, embedder: Any) -> None:
        """Initialize the session manager. Called during FastAPI lifespan startup.

        Loads and prepares the @recipes bundle with custom providers.
        Subsequent session creations reuse the prepared bundle.
        """
        self._db_repo = db_repo
        self._embedder = embedder

        # Pre-load and prepare the recipes bundle for fast session creation
        await self._get_recipes_bundle()

        logger.info(
            "SessionManager started with providers: %s",
            [p.module for p in self._config.providers],
        )

    async def shutdown(self) -> None:
        """Clean up all active sessions. Called during FastAPI lifespan shutdown."""
        for workflow_id in list(self._active_sessions.keys()):
            await self.close_workflow(workflow_id)
        logger.info("SessionManager shut down, all sessions cleaned up")

    # -- Bundle Loading & Composition ------------------------------------

    async def _get_recipes_bundle(self) -> Any:
        """Get the prepared @recipes bundle with custom providers.

        Cached for performance - prepare() downloads modules, which is expensive.
        """
        if "recipes" not in self._prepared_bundles:
            logger.info("Loading @recipes bundle...")

            # 1. Load @recipes bundle (includes foundation + tool-recipes)
            recipes_bundle = await load_bundle(
                "git+https://github.com/microsoft/amplifier-bundle-recipes@main"
            )
            logger.info("Loaded @recipes bundle: %s", recipes_bundle.name)

            # 2. Create override bundle with custom app config
            override = self._create_override_bundle()

            # 3. Compose recipes + override
            composed = recipes_bundle.compose(override)
            logger.info("Composed bundle with custom providers")

            # 4. Prepare (download/install modules) - cache this result
            await composed.prepare(install_deps=True)
            logger.info("Prepared bundle (modules installed)")

            self._prepared_bundles["recipes"] = composed

        return self._prepared_bundles["recipes"]

    def _create_override_bundle(self) -> Bundle:
        """Create override bundle with custom providers and default_provider.

        Follows thin bundle pattern - only declares what's unique to this app:
        - Custom providers (Azure, Anthropic) from settings.yaml
        - default_provider selection (REQUIRED to activate providers)

        Foundation provides (inherited via compose):
        - orchestrator config (loop-streaming)
        - context config (context-simple)

        Does NOT include:
        - tool-recipes (comes from @recipes)
        - Foundation tools (come via @recipes -> foundation)
        """
        # Build providers list from app config
        providers = []
        for prov in self._config.providers:
            provider_config = {
                "module": prov.module,
                "config": dict(prov.config),
            }

            # Add source URL for module download
            # These are standard Amplifier provider modules
            if prov.module == "provider-azure-openai":
                provider_config["source"] = (
                    "git+https://github.com/microsoft/amplifier-module-provider-azure-openai@main"
                )
            elif prov.module == "provider-anthropic":
                provider_config["source"] = (
                    "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main"
                )

            providers.append(provider_config)

        # Find active provider (priority=1) - REQUIRED to activate providers
        active_provider = next(
            (p.module for p in self._config.providers if p.is_active),
            self._config.providers[0].module if self._config.providers else None,
        )

        # Override bundle: Providers + explicit orchestrator config
        # Use loop-basic instead of loop-streaming (simpler, no version issues)
        return Bundle(
            name="agent-catalogue-config",
            version="1.0.0",
            providers=providers,
            session={
                "default_provider": active_provider,
                "orchestrator": "loop-basic",  # Simple orchestrator, no version issues
                "context": "context-simple",
            },
        )

    # -- Session Creation -----------------------------------------------

    async def _create_session_from_bundle(
        self,
        bundle_type: str = "recipes",
        session_id: str | None = None,
        parent_id: str | None = None,
    ) -> AmplifierSession:
        """Create session from a prepared bundle.

        Args:
            bundle_type: Which prepared bundle to use ("recipes" for now)
            session_id: Optional specific session ID
            parent_id: Optional parent session ID for sub-agents

        Returns:
            Initialized AmplifierSession ready for execution
        """
        if bundle_type == "recipes":
            prepared_bundle = await self._get_recipes_bundle()
        else:
            raise ValueError(f"Unknown bundle type: {bundle_type}")

        # Get mount plan from prepared bundle
        mount_plan = prepared_bundle.to_mount_plan()
        logger.info(
            "Mount plan has %d providers, %d tools",
            len(mount_plan.get("providers", [])),
            len(mount_plan.get("tools", [])),
        )

        # Create session
        session = AmplifierSession(
            config=mount_plan,
            session_id=session_id,
            parent_id=parent_id,
        )

        # CRITICAL: Mount source resolver BEFORE initialize()
        # This allows loader to find modules in bundle cache
        if hasattr(prepared_bundle, "resolver"):
            await session.coordinator.mount("module-source-resolver", prepared_bundle.resolver)
            logger.debug("Mounted bundle source resolver to session")

        # Now initialize can find modules
        await session.initialize()

        logger.info(
            "Created session %s from %s bundle (parent=%s)",
            session.session_id,
            bundle_type,
            parent_id or "none",
        )

        return session

    # -- Recipe Execution Sessions --------------------------------------

    async def _create_session(self, session_id: str | None = None) -> AmplifierSession:
        """Create a temporary session with recipes bundle.

        Used by recipe endpoints to access the recipes tool.
        This is a lightweight wrapper around create_recipe_session.

        Returns:
            Initialized AmplifierSession with recipes tool mounted
        """
        return await self.create_recipe_session(session_id=session_id)

    def _create_spawn_callback_for_recipes(self):
        """Create a spawn callback for recipe execution sessions.

        The recipes tool requires a 'session.spawn' capability to delegate work
        to sub-agents. This method returns a callback that recipes can use.

        Returns:
            Async function that creates and executes a child session
        """

        async def spawn_callback(
            agent_name: str, instruction: str, parent_session, **kwargs
        ) -> str:
            """Spawn a child session for recipe sub-agent delegation.

            Args:
                agent_name: Agent name or bundle path
                instruction: Instruction to execute
                parent_session: Parent AmplifierSession
                **kwargs: Additional arguments from recipes tool (ignored)

            Returns:
                Response string from the child session
            """
            logger.info(
                "Recipe spawn callback: agent=%s, parent=%s",
                agent_name,
                parent_session.session_id,
            )

            # Create child session from recipes bundle
            child = await self._create_session_from_bundle(
                bundle_type="recipes",
                parent_id=parent_session.session_id,
            )

            try:
                # Execute instruction on child
                response = await child.execute(instruction)
                return response
            finally:
                # Clean up child session
                await child.cleanup()

        return spawn_callback

    async def create_recipe_session(
        self,
        session_id: str | None = None,
    ) -> AmplifierSession:
        """Create a fresh session for recipe execution.

        Each recipe execution gets its own isolated session with:
        - tool-recipes from @recipes bundle
        - All foundation tools (filesystem, bash, web, delegate)
        - Custom Azure/Anthropic providers
        - recipe-author and result-validator agents

        Recommended pattern: Create new session per recipe execution.
        """
        return await self._create_session_from_bundle(
            bundle_type="recipes",
            session_id=session_id,
        )

    # -- Workflow Sessions ----------------------------------------------

    async def create_workflow(self, workflow_id: str) -> AmplifierSession:
        """Create a persistent workflow session with catalogue tools.

        The session persists across multiple execute_step() calls.
        Context accumulates - each step sees prior conversation history.
        """
        session = await self._create_session_from_bundle(
            bundle_type="recipes",
            session_id=workflow_id,
        )

        # Mount catalogue tools with app dependencies
        tools = create_catalogue_tools(self._db_repo, self._embedder)
        for tool in tools:
            await session.coordinator.mount("tools", tool, name=tool.name)

        # Register SSE hooks for real-time streaming
        unregisters = self.sse_bridge.register_hooks(session, workflow_id)

        self._active_sessions[workflow_id] = session
        self._session_locks[workflow_id] = asyncio.Lock()
        self._hook_unregisters[workflow_id] = unregisters

        logger.info("Created workflow session: %s", workflow_id)
        return session

    async def execute_step(self, workflow_id: str, prompt: str) -> str:
        """Execute a step within a workflow session.

        Thread-safe via per-session asyncio.Lock.
        Context accumulates across calls.
        """
        session = self._active_sessions.get(workflow_id)
        if not session:
            raise ValueError(f"No active workflow session: {workflow_id}")

        async with self._session_locks[workflow_id]:
            response = await session.execute(prompt)

        # Persist transcript after each step
        self._save_session(workflow_id, session)
        return response

    async def close_workflow(self, workflow_id: str) -> None:
        """Clean up a completed workflow session."""
        session = self._active_sessions.pop(workflow_id, None)
        self._session_locks.pop(workflow_id, None)

        # Unregister hooks
        for unreg in self._hook_unregisters.pop(workflow_id, []):
            try:
                unreg()
            except Exception:
                pass

        # Clean up SSE queue
        self.sse_bridge.remove_queue(workflow_id)

        # Final save before cleanup
        if session:
            self._save_session(workflow_id, session, final=True)
            try:
                await session.cleanup()
            except Exception:
                logger.debug("Error cleaning up session %s", workflow_id, exc_info=True)

        logger.info("Closed workflow session: %s", workflow_id)

    def get_session(self, workflow_id: str) -> AmplifierSession | None:
        """Get an active workflow session by ID."""
        return self._active_sessions.get(workflow_id)

    # -- Sub-Agent Spawning ---------------------------------------------

    async def spawn_specialist(
        self,
        parent: AmplifierSession,
        agent_name: str,
        instruction: str,
    ) -> str:
        """Spawn a specialist sub-agent from a parent workflow session.

        Creates a child session with:
        - The agent's system prompt + domain knowledge injected
        - Catalogue tools mounted (can search/access the catalogue)
        - parent_id set for event lineage tracking
        - SSE hooks registered (events route to parent's queue)

        The child session is cleaned up after execution.
        """
        logger.info(
            "Spawning specialist agent=%s instruction_length=%d",
            agent_name,
            len(instruction),
        )
        system_prompt = self._build_agent_prompt(agent_name)

        child = await self._create_session_from_bundle(
            bundle_type="recipes",
            parent_id=parent.session_id,
        )
        logger.info("Created child session: %s (parent=%s)", child.session_id, parent.session_id)

        # Inject specialist system prompt
        context = child.coordinator.get("context")
        await context.add_message({"role": "system", "content": system_prompt})

        # Mount catalogue tools
        logger.info(
            "Creating catalogue tools (db_repo=%s, embedder=%s)",
            type(self._db_repo).__name__,
            type(self._embedder).__name__,
        )
        tools = create_catalogue_tools(self._db_repo, self._embedder)
        logger.info("Created %d tools: %s", len(tools), [t.name for t in tools])

        for tool in tools:
            logger.info("Mounting tool: %s", tool.name)
            await child.coordinator.mount("tools", tool, name=tool.name)
            logger.info("✓ Mounted tool: %s", tool.name)

        # Register SSE hooks (events carry parent_id -> route to parent's queue)
        parent_workflow_id = parent.session_id
        child_unregisters = self.sse_bridge.register_hooks(child, parent_workflow_id)

        try:
            logger.info("Executing instruction on %s...", agent_name)
            response = await child.execute(instruction)
            logger.info("Specialist %s completed successfully", agent_name)
            return response
        finally:
            for unreg in child_unregisters:
                try:
                    unreg()
                except Exception:
                    pass
            await child.cleanup()

    # -- One-Shot Sessions ----------------------------------------------

    async def run_one_shot(
        self,
        agent_name: str,
        instruction: str,
    ) -> str:
        """Run a one-shot session with a specialist agent.

        Creates a fresh session, executes once, cleans up.
        No persistent state. Good for independent operations like search.
        """
        logger.info(
            "One-shot session: agent=%s instruction_length=%d",
            agent_name,
            len(instruction),
        )
        system_prompt = self._build_agent_prompt(agent_name)

        session = await self._create_session_from_bundle(bundle_type="recipes")

        context = session.coordinator.get("context")
        await context.add_message({"role": "system", "content": system_prompt})

        # Mount catalogue tools
        tools = create_catalogue_tools(self._db_repo, self._embedder)
        for tool in tools:
            await session.coordinator.mount("tools", tool, name=tool.name)

        try:
            return await session.execute(instruction)
        finally:
            await session.cleanup()

    # -- One-Shot Streaming Sessions ------------------------------------

    async def run_one_shot_streaming(
        self,
        agent_name: str,
        instruction: str,
        event_queue: asyncio.Queue,
    ) -> str:
        """Run a one-shot session with real-time event streaming.

        Same as run_one_shot but registers SSE hooks that push kernel
        events (thinking, tool calls, content deltas) to the provided
        queue for real-time UI feedback.
        """
        logger.info(
            "One-shot streaming session: agent=%s instruction_length=%d",
            agent_name,
            len(instruction),
        )
        system_prompt = self._build_agent_prompt(agent_name)

        session = await self._create_session_from_bundle(bundle_type="recipes")

        context = session.coordinator.get("context")
        await context.add_message({"role": "system", "content": system_prompt})

        # Mount catalogue tools
        tools = create_catalogue_tools(self._db_repo, self._embedder)
        for tool in tools:
            await session.coordinator.mount("tools", tool, name=tool.name)

        # Register SSE hooks for real-time streaming
        sid = session.session_id
        logger.info("Registering SSE hooks for session %s (agent=%s)", sid, agent_name)
        unregisters = self.sse_bridge.register_hooks(session, sid, agent_name=agent_name)
        logger.info("SSE hooks registered: %d unregister callbacks", len(unregisters))
        # Point the bridge queue to the caller's event_queue
        self.sse_bridge._queues[sid] = event_queue
        logger.info("SSE bridge queue mapped for session %s", sid)

        try:
            response = await session.execute(instruction)
            return response
        finally:
            for unreg in unregisters:
                try:
                    unreg()
                except Exception:
                    pass
            self.sse_bridge.remove_queue(sid)
            await session.cleanup()

    # -- Session Persistence --------------------------------------------

    def _save_session(
        self,
        workflow_id: str,
        session: AmplifierSession,
        final: bool = False,
    ) -> None:
        """Persist session transcript and metadata. Best-effort, never throws."""
        try:
            context = session.coordinator.get("context")
            if not context:
                return

            # get_messages() returns the full uncompacted history
            messages = (
                asyncio.get_event_loop().run_until_complete(context.get_messages())
                if not asyncio.get_event_loop().is_running()
                else []
            )

            # For running event loops, try sync access if available
            if not messages and hasattr(context, "messages"):
                messages = context.messages

            if not messages:
                return

            # Filter out system messages for the transcript
            transcript = [m for m in messages if m.get("role") not in ("system", "developer")]

            metadata = {
                "session_id": workflow_id,
                "created_at": datetime.now(UTC).isoformat(),
                "turn_count": len([m for m in transcript if m.get("role") == "user"]),
                "status": "completed" if final else "active",
                "providers": [p.module for p in self._config.providers],
            }

            self.session_store.save(workflow_id, transcript, metadata)
        except Exception:
            logger.debug("Failed to save session %s", workflow_id, exc_info=True)

    # -- Agent Prompt Building ------------------------------------------

    def _build_agent_prompt(self, agent_name: str) -> str:
        """Load agent instruction + skill knowledge files into a system prompt.

        Uses caching to avoid re-reading files on every spawn.
        """
        if agent_name in self._agent_cache:
            return self._agent_cache[agent_name]

        # Load agent instruction
        agent_file = self._agents_dir / f"{agent_name}.md"
        if not agent_file.exists():
            raise ValueError(f"Agent definition not found: {agent_file}")
        instruction = agent_file.read_text(encoding="utf-8")

        # Load skill/knowledge files
        skills = AGENT_SKILLS.get(agent_name, [])
        skill_parts = []
        for skill_filename in skills:
            skill_file = self._context_dir / skill_filename
            if skill_file.exists():
                skill_parts.append(skill_file.read_text(encoding="utf-8"))

        # Combine: instruction + knowledge
        if skill_parts:
            prompt = (
                instruction
                + "\n\n---\n\n# Reference Knowledge\n\n"
                + "\n\n---\n\n".join(skill_parts)
            )
        else:
            prompt = instruction

        self._agent_cache[agent_name] = prompt
        return prompt
