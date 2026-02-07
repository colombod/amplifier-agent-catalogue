"""SessionManager: core Amplifier integration for the Agent Catalogue web app.

Manages Amplifier session lifecycle for multi-step workflows:
- Uses amplifier-foundation for module resolution (downloads providers,
  orchestrator, context modules from git on first run, caches locally)
- Creates persistent workflow sessions with catalogue tools mounted
- Spawns specialist sub-agents from parent sessions
- Persists session transcripts and metadata for observability
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from amplifier_core import AmplifierSession
from amplifier_foundation.bundle import BundleModuleResolver
from amplifier_foundation.modules.activator import ModuleActivator

from agent_catalogue.config import Config
from agent_catalogue.paths import get_agents_dir, get_cache_dir, get_context_dir
from agent_catalogue.session_store import SessionStore
from agent_catalogue.sse_bridge import SSEBridge
from agent_catalogue.tools import create_catalogue_tools

logger = logging.getLogger(__name__)

# Git sources for Amplifier modules we depend on
MODULE_SOURCES: dict[str, str] = {
    "provider-azure-openai": "git+https://github.com/microsoft/amplifier-module-provider-azure-openai@main",
    "provider-anthropic": "git+https://github.com/microsoft/amplifier-module-provider-anthropic@main",
    "loop-streaming": "git+https://github.com/microsoft/amplifier-module-loop-streaming@main",
    "context-simple": "git+https://github.com/microsoft/amplifier-module-context-simple@main",
}

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
    """Manages Amplifier sessions for the Agent Catalogue web app.

    Uses amplifier-foundation's ModuleActivator to download and cache
    Amplifier modules (providers, orchestrator, context) from git on first
    startup. Subsequent startups reuse the local cache.

    Provides three session patterns:
    1. Workflow sessions: persist across multiple execute() calls
    2. Sub-agent spawning: fork specialist agents from a parent session
    3. One-shot sessions: create, execute once, cleanup
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._mount_plan: dict[str, Any] = {}
        self._db_repo: Any = None
        self._embedder: Any = None
        self._resolver: BundleModuleResolver | None = None
        self._active_sessions: dict[str, AmplifierSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._hook_unregisters: dict[str, list] = {}
        self.sse_bridge = SSEBridge()
        self.session_store = SessionStore()
        self._agents_dir = get_agents_dir()
        self._context_dir = get_context_dir()
        self._agent_cache: dict[str, str] = {}
        self._cache_dir = get_cache_dir()

    async def startup(self, db_repo: Any, embedder: Any) -> None:
        """Initialize the session manager. Called during FastAPI lifespan startup.

        Downloads and caches Amplifier modules on first run. Subsequent calls
        reuse the local cache (~/.amplifier/cache/).
        """
        self._db_repo = db_repo
        self._embedder = embedder
        self._mount_plan = self._build_mount_plan()

        # Activate modules: download from git (first time) or use cache
        self._resolver = await self._activate_modules()

        logger.info(
            "SessionManager started with providers: %s",
            [p["module"] for p in self._mount_plan.get("providers", [])],
        )

    async def shutdown(self) -> None:
        """Clean up all active sessions. Called during FastAPI lifespan shutdown."""
        for workflow_id in list(self._active_sessions.keys()):
            await self.close_workflow(workflow_id)
        logger.info("SessionManager shut down, all sessions cleaned up")

    # -- Module Activation -----------------------------------------------

    async def _activate_modules(self) -> BundleModuleResolver:
        """Download and activate all Amplifier modules we need.

        Uses amplifier-foundation's ModuleActivator which handles:
        - Git shallow cloning into ~/.amplifier/cache/
        - Cache hit detection (skips clone if already present)
        - sys.path management so the kernel's ModuleLoader can find them
        - pip install of module dependencies via uv
        """
        activator = ModuleActivator(cache_dir=self._cache_dir)

        # Collect modules from the mount plan that need activation
        modules_to_activate = []

        # Orchestrator
        orch_id = self._mount_plan["session"]["orchestrator"]
        if orch_id in MODULE_SOURCES:
            modules_to_activate.append({"module": orch_id, "source": MODULE_SOURCES[orch_id]})
            logger.info("Activating module %s from %s", orch_id, MODULE_SOURCES[orch_id])

        # Context
        ctx_id = self._mount_plan["session"]["context"]
        if ctx_id in MODULE_SOURCES:
            modules_to_activate.append({"module": ctx_id, "source": MODULE_SOURCES[ctx_id]})
            logger.info("Activating module %s from %s", ctx_id, MODULE_SOURCES[ctx_id])

        # Providers
        for prov in self._mount_plan.get("providers", []):
            mod_id = prov["module"]
            if mod_id in MODULE_SOURCES:
                modules_to_activate.append({"module": mod_id, "source": MODULE_SOURCES[mod_id]})
                logger.info("Activating module %s from %s", mod_id, MODULE_SOURCES[mod_id])

        logger.info(
            "Activating %d Amplifier modules (cached in %s)",
            len(modules_to_activate),
            self._cache_dir,
        )

        # activate_all downloads + installs + returns {module_id: Path}
        module_paths = await activator.activate_all(modules_to_activate)

        # Build a resolver the kernel's ModuleLoader can use
        # The activator is passed so lazy resolution works for any
        # module not pre-activated (e.g. spawned agents requesting tools)
        resolver = BundleModuleResolver(module_paths, activator=activator)

        logger.info("Activated modules: %s", list(module_paths.keys()))
        return resolver

    # -- Session Creation (internal) -------------------------------------

    async def _create_session(
        self,
        session_id: str | None = None,
        parent_id: str | None = None,
    ) -> AmplifierSession:
        """Create and initialize an AmplifierSession with module resolver mounted.

        This is the canonical session creation path. All public methods
        (create_workflow, spawn_specialist, run_one_shot) go through here.
        """
        session = AmplifierSession(
            config=self._mount_plan,
            session_id=session_id,
            parent_id=parent_id,
        )

        # Mount the module resolver BEFORE initialize() so the kernel's
        # ModuleLoader can find our git-sourced modules
        if self._resolver:
            await session.coordinator.mount("module-source-resolver", self._resolver)

        await session.initialize()
        return session

    # -- Workflow Sessions -----------------------------------------------

    async def create_workflow(self, workflow_id: str) -> AmplifierSession:
        """Create a persistent workflow session with catalogue tools.

        The session persists across multiple execute_step() calls.
        Context accumulates - each step sees prior conversation history.
        """
        session = await self._create_session(session_id=workflow_id)

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

    # -- Sub-Agent Spawning ----------------------------------------------

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

        child = await self._create_session(parent_id=parent.session_id)
        logger.info("Created child session: %s (parent=%s)", child.session_id, parent.session_id)

        # Inject specialist system prompt
        context = child.coordinator.get("context")
        await context.add_message({"role": "system", "content": system_prompt})

        # Mount catalogue tools WITH VERIFICATION
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

    # -- One-Shot Sessions -----------------------------------------------

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

        session = await self._create_session()

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

    # -- One-Shot Streaming Sessions -------------------------------------

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

        session = await self._create_session()

        context = session.coordinator.get("context")
        await context.add_message({"role": "system", "content": system_prompt})

        # Mount catalogue tools
        tools = create_catalogue_tools(self._db_repo, self._embedder)
        for tool in tools:
            await session.coordinator.mount("tools", tool, name=tool.name)

        # Register SSE hooks for real-time streaming
        # Use the session's own ID as the routing key
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

    # -- Session Persistence ---------------------------------------------

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
                "providers": [p["module"] for p in self._mount_plan.get("providers", [])],
            }

            self.session_store.save(workflow_id, transcript, metadata)
        except Exception:
            logger.debug("Failed to save session %s", workflow_id, exc_info=True)

    # -- Agent Prompt Building -------------------------------------------

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

    # -- Mount Plan Building ---------------------------------------------

    def _build_mount_plan(self) -> dict[str, Any]:
        """Build the Amplifier mount plan from app config.

        Providers are already in mount-plan format from settings.yaml,
        so we pass them through directly.
        """
        providers = []
        for prov in self._config.providers:
            providers.append(
                {
                    "module": prov.module,
                    "config": dict(prov.config),  # copy to avoid mutation
                }
            )

        logger.info("Mount plan built with %d provider(s)", len(providers))
        return {
            "session": {
                "orchestrator": "loop-streaming",
                "context": "context-simple",
            },
            "providers": providers,
            "orchestrator": {
                "config": {
                    "max_iterations": 15,
                },
            },
            "context": {
                "config": {
                    "max_tokens": 200_000,
                    "compact_threshold": 0.85,
                },
            },
            "tools": [],
            "hooks": [],
        }
