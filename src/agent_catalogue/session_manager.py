"""SessionManager: core Amplifier integration for the Agent Catalogue web app.

Manages Amplifier session lifecycle for multi-step workflows:
- Builds the mount plan (providers, orchestrator, context) from config
- Creates persistent workflow sessions with catalogue tools mounted
- Spawns specialist sub-agents from parent sessions
- Handles session cleanup and resource management
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any

from amplifier_core import AmplifierSession
from amplifier_core.models import ToolResult

from agent_catalogue.config import Config
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
}


class SessionManager:
    """Manages Amplifier sessions for the Agent Catalogue web app.

    Provides two session patterns:
    1. Workflow sessions: persist across multiple execute() calls, context accumulates
    2. Sub-agent spawning: fork specialist agents from a parent workflow session
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._mount_plan: dict[str, Any] = {}
        self._db_repo: Any = None
        self._embedder: Any = None
        self._active_sessions: dict[str, AmplifierSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._hook_unregisters: dict[str, list] = {}
        self.sse_bridge = SSEBridge()
        self._agents_dir = Path(__file__).parent.parent.parent / "agents"
        self._context_dir = Path(__file__).parent.parent.parent / "context"
        self._agent_cache: dict[str, str] = {}

    async def startup(self, db_repo: Any, embedder: Any) -> None:
        """Initialize the session manager. Called during FastAPI lifespan startup."""
        self._db_repo = db_repo
        self._embedder = embedder
        self._mount_plan = self._build_mount_plan()
        logger.info("SessionManager started with providers: %s",
                     [p["module"] for p in self._mount_plan.get("providers", [])])

    async def shutdown(self) -> None:
        """Clean up all active sessions. Called during FastAPI lifespan shutdown."""
        for workflow_id in list(self._active_sessions.keys()):
            await self.close_workflow(workflow_id)
        logger.info("SessionManager shut down, all sessions cleaned up")

    # ── Workflow Sessions ──────────────────────────────────────────────

    async def create_workflow(self, workflow_id: str) -> AmplifierSession:
        """Create a persistent workflow session with catalogue tools.

        The session persists across multiple execute_step() calls.
        Context accumulates - each step sees prior conversation history.
        """
        session = AmplifierSession(
            config=self._mount_plan,
            session_id=workflow_id,
        )
        await session.initialize()

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
            return await session.execute(prompt)

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

        if session:
            try:
                await session.cleanup()
            except Exception:
                logger.debug("Error cleaning up session %s", workflow_id, exc_info=True)

        logger.info("Closed workflow session: %s", workflow_id)

    def get_session(self, workflow_id: str) -> AmplifierSession | None:
        """Get an active workflow session by ID."""
        return self._active_sessions.get(workflow_id)

    # ── Sub-Agent Spawning ─────────────────────────────────────────────

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
        system_prompt = self._build_agent_prompt(agent_name)

        child = AmplifierSession(
            config=self._mount_plan,
            parent_id=parent.session_id,
        )
        await child.initialize()

        # Inject specialist system prompt
        context = child.coordinator.get("context")
        await context.add_message({"role": "system", "content": system_prompt})

        # Mount catalogue tools
        tools = create_catalogue_tools(self._db_repo, self._embedder)
        for tool in tools:
            await child.coordinator.mount("tools", tool, name=tool.name)

        # Register SSE hooks (events carry parent_id → route to parent's queue)
        parent_workflow_id = parent.session_id
        child_unregisters = self.sse_bridge.register_hooks(child, parent_workflow_id)

        try:
            response = await child.execute(instruction)
            return response
        finally:
            for unreg in child_unregisters:
                try:
                    unreg()
                except Exception:
                    pass
            await child.cleanup()

    # ── One-Shot Sessions ──────────────────────────────────────────────

    async def run_one_shot(
        self,
        agent_name: str,
        instruction: str,
    ) -> str:
        """Run a one-shot session with a specialist agent.

        Creates a fresh session, executes once, cleans up.
        No persistent state. Good for independent operations like search.
        """
        system_prompt = self._build_agent_prompt(agent_name)

        session = AmplifierSession(config=self._mount_plan)
        await session.initialize()

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

    # ── Agent Prompt Building ──────────────────────────────────────────

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
            prompt = instruction + "\n\n---\n\n# Reference Knowledge\n\n" + "\n\n---\n\n".join(skill_parts)
        else:
            prompt = instruction

        self._agent_cache[agent_name] = prompt
        return prompt

    # ── Mount Plan Building ────────────────────────────────────────────

    def _build_mount_plan(self) -> dict[str, Any]:
        """Build the Amplifier mount plan from app config."""
        providers = []

        # Azure OpenAI provider (primary)
        azure_config: dict[str, Any] = {
            "azure_endpoint": self._config.azure_openai.endpoint,
            "api_version": self._config.azure_openai.api_version,
            "default_model": self._config.azure_openai.chat_deployment,
            "priority": 1,
        }
        if self._config.azure_openai.use_rbac:
            azure_config["use_default_credential"] = True
        elif self._config.azure_openai.api_key:
            azure_config["api_key"] = self._config.azure_openai.api_key

        providers.append({
            "module": "provider-azure-openai",
            "config": azure_config,
        })

        # Anthropic provider (fallback)
        if self._config.anthropic.api_key:
            providers.append({
                "module": "provider-anthropic",
                "config": {
                    "default_model": self._config.anthropic.default_model,
                    "api_key": self._config.anthropic.api_key,
                    "priority": 2,
                },
            })

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
