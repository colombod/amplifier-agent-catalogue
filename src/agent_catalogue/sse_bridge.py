"""SSE Bridge: forwards Amplifier kernel events to web clients via asyncio queues.

Registers as a hook handler on AmplifierSession, capturing real events
emitted by the loop-streaming orchestrator through hooks.emit():

  tool:pre / tool:post / tool:error    - Tool invocations
  content_block:start / :end           - LLM response content blocks
  execution:start / execution:end      - Orchestrator lifecycle
  prompt:submit / orchestrator:complete - Turn lifecycle
  provider:request / provider:response  - LLM API calls

NOTE: content_block:delta and thinking:delta are NOT emitted through
hooks.emit() by the orchestrator - they only exist in the CLI's
streaming UI hook which reads from the raw provider stream.  We use
content_block:end (which carries the full block including thinking
text) to surface agent reasoning to the UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from amplifier_core.models import HookResult

logger = logging.getLogger(__name__)

# Events the loop-streaming orchestrator actually emits via hooks.emit()
KERNEL_EVENTS = frozenset(
    [
        "tool:pre",
        "tool:post",
        "tool:error",
        "content_block:start",
        "content_block:end",
        "execution:start",
        "execution:end",
        "prompt:submit",
        "orchestrator:complete",
        "provider:request",
        "provider:response",
        "session:start",
        "session:end",
        "session:fork",
    ]
)


class SSEBridge:
    """Forwards Amplifier kernel events to asyncio queues for SSE streaming."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}

    def create_queue(self, workflow_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        """Create an event queue for a workflow. Returns the queue for consumption."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._queues[workflow_id] = queue
        return queue

    def remove_queue(self, workflow_id: str) -> None:
        """Remove a workflow's event queue."""
        self._queues.pop(workflow_id, None)

    def has_queue(self, workflow_id: str) -> bool:
        """Check if a workflow has an active SSE queue."""
        return workflow_id in self._queues

    async def signal_done(self, workflow_id: str) -> None:
        """Signal that the workflow is complete (sends sentinel to queue)."""
        queue = self._queues.get(workflow_id)
        if queue:
            await queue.put(None)

    def register_hooks(self, session: Any, workflow_id: str, agent_name: str | None = None) -> list:
        """Register event hooks on an AmplifierSession for SSE forwarding.

        Args:
            session: The AmplifierSession to hook into.
            workflow_id: Routing key for the event queue.
            agent_name: Optional agent identity tag added to every event.

        Returns list of unregister callables for cleanup.
        """
        logger.info("=" * 60)
        logger.info("SSE BRIDGE: register_hooks called")
        logger.info("  session_id: %s", session.session_id)
        logger.info("  workflow_id: %s", workflow_id)
        logger.info("  agent_name: %s", agent_name)
        logger.info("  has_coordinator: %s", hasattr(session, "coordinator"))
        logger.info(
            "  has_hooks: %s",
            hasattr(session.coordinator, "hooks") if hasattr(session, "coordinator") else False,
        )

        unregisters = []
        registered = []
        failed = []

        async def handler(event: str, data: dict[str, Any]) -> HookResult:
            # Route to the workflow queue
            target = data.get("parent_id") or workflow_id
            if target not in self._queues:
                target = workflow_id
            queue = self._queues.get(target)
            if queue:
                try:
                    serialized = _serialize_event(event, data, agent_name=agent_name)
                    if serialized:
                        logger.debug("SSE: Putting event %s to queue (workflow=%s)", event, target)
                        await queue.put(serialized)
                except Exception:
                    logger.error("Failed to serialize event %s", event, exc_info=True)
            else:
                logger.warning("SSE: No queue for workflow %s (event=%s)", target, event)
            return HookResult(action="continue")

        for evt in KERNEL_EVENTS:
            try:
                unreg = session.coordinator.hooks.register(
                    evt, handler, name=f"sse_{evt}", priority=900
                )
                unregisters.append(unreg)
                registered.append(evt)
                logger.debug("  ✓ Registered hook: %s", evt)
            except Exception as e:
                failed.append(evt)
                logger.error("  ✗ Failed to register hook %s: %s", evt, e, exc_info=True)

        logger.info("SSE BRIDGE: Registration complete")
        logger.info("  Registered: %d events: %s", len(registered), registered[:5])
        logger.info("  Failed: %d events: %s", len(failed), failed)
        logger.info("=" * 60)

        if not registered:
            logger.error("SSE BRIDGE: NO HOOKS REGISTERED! This will break streaming.")

        return unregisters


def _serialize_event(
    event: str, data: dict[str, Any], agent_name: str | None = None
) -> dict[str, Any] | None:
    """Extract UI-relevant fields from kernel event data.

    If *agent_name* is provided it is injected into the ``data`` dict of
    every returned event so the UI can display which agent produced it.

    Returns None for events that have no useful UI representation.
    """
    result = _build_event(event, data)

    # Inject agent identity into every event for UI display
    if result and agent_name:
        result["data"]["agent_name"] = agent_name

    return result


def _build_event(event: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Map a kernel event to a UI-friendly dict (no agent tagging)."""

    if event == "tool:pre":
        tool_name = data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {})
        # Build a human-readable preview of what the tool is doing
        preview = ""
        if isinstance(tool_input, dict):
            if "query" in tool_input:
                preview = f'"{tool_input["query"]}"'
            elif "text" in tool_input:
                preview = f"({len(tool_input['text'])} chars)"
            elif "agent_id" in tool_input:
                preview = tool_input["agent_id"]
            elif "slug" in tool_input:
                preview = tool_input["slug"]
        return {
            "event": "tool:pre",
            "data": {
                "tool_name": tool_name,
                "input_preview": preview or str(tool_input)[:200],
            },
        }

    if event == "tool:post":
        tool_name = data.get("tool_name", "unknown")
        # Orchestrator passes result in 'result' field, not 'tool_result'
        tool_result = data.get("result", {})

        # COMPREHENSIVE DEBUG
        logger.info("=" * 60)
        logger.info("tool:post EVENT SERIALIZATION: %s", tool_name)
        logger.info("  data keys: %s", list(data.keys()))
        logger.info("  tool_result type: %s", type(tool_result))
        if isinstance(tool_result, dict):
            logger.info("  tool_result keys: %s", list(tool_result.keys()))
            logger.info("  has 'error': %s", "error" in tool_result)
            logger.info(
                "  error VALUE: %r (type=%s)",
                tool_result.get("error"),
                type(tool_result.get("error")),
            )
            logger.info("  has 'output': %s", "output" in tool_result)

        # ToolResult can be either a dict or a Pydantic ToolResult model
        if isinstance(tool_result, dict):
            # Dict form (serialized ToolResult)
            has_error = bool(tool_result.get("error"))
            success = tool_result.get("success", True) if not has_error else False
            output = tool_result.get("output", "")
            logger.info("  tool_result: dict form")
        elif hasattr(tool_result, "success") and hasattr(tool_result, "output"):
            # Pydantic ToolResult model
            success = tool_result.success
            output = tool_result.output
            logger.info("  tool_result: Pydantic model form")
        else:
            # Unknown format - treat as failure
            success = False
            output = ""
            logger.warning("  tool_result: UNKNOWN FORMAT (not dict, not ToolResult model)")

        logger.info("  success: %s", success)
        logger.info("  output type: %s", type(output))
        if isinstance(output, dict):
            logger.info("  output keys: %s", list(output.keys()))
            logger.info(
                "  output content preview: %s",
                {
                    k: (
                        v
                        if not isinstance(v, (list, str)) or len(str(v)) < 50
                        else f"{type(v).__name__}[{len(v)}]"
                    )
                    for k, v in list(output.items())[:5]
                },
            )

        # Build informative summary based on tool output structure
        summary = ""
        if isinstance(output, dict):
            # search_similar returns {"count": N, "agents": [...]}
            if "count" in output and "agents" in output:
                count = output.get("count", 0)
                agents_list = output.get("agents", [])
                logger.info(
                    "  → search_similar pattern: count=%d, agents_len=%d", count, len(agents_list)
                )

                if count == 0:
                    summary = "no results"
                elif count == 1 and agents_list:
                    agent_name = agents_list[0].get("name", "Unknown")
                    summary = f'found "{agent_name}"'
                else:
                    summary = f"found {count} agents"
            # get_agent_content returns {"agent_name": X, "content": Y, ...}
            elif "agent_name" in output and "content" in output:
                name = output.get("agent_name", "Unknown")
                content_len = len(output.get("content", ""))
                logger.info(
                    "  → get_agent_content pattern: name=%s, content_len=%d", name, content_len
                )
                summary = f'"{name}" ({content_len} chars)'
            # Generic dict
            else:
                keys = list(output.keys())
                summary = f"{len(output)} fields ({', '.join(keys[:3])})"
                logger.info("  → generic dict: %d keys: %s", len(keys), keys)
        elif isinstance(output, list):
            summary = f"{len(output)} items"
        elif isinstance(output, str):
            summary = f"{len(output)} chars"
        elif not output:
            summary = "empty output"
            logger.warning("  → EMPTY OUTPUT!")
        else:
            summary = f"type={type(output).__name__}"

        logger.info("  FINAL summary: %r", summary)
        logger.info("=" * 60)

        return {
            "event": "tool:post",
            "data": {
                "tool_name": tool_name,
                "success": success,
                "output_preview": summary or str(output)[:200],
            },
        }

    if event == "tool:error":
        return {
            "event": "tool:error",
            "data": {
                "tool_name": data.get("tool_name", "unknown"),
                "error": str(data.get("error", ""))[:300],
            },
        }

    if event == "content_block:start":
        block_type = data.get("block_type", "text")
        return {
            "event": "content_block:start",
            "data": {
                "block_type": block_type,
                "block_index": data.get("block_index", 0),
                "total_blocks": data.get("total_blocks", 1),
            },
        }

    if event == "content_block:end":
        # This is where the real content lives - the full block
        block = data.get("block", {})

        # DEBUG: Log everything we're receiving
        logger.info("=" * 80)
        logger.info("content_block:end - FULL EVENT DATA DUMP:")
        logger.info("Block type: %s", type(block))
        logger.info("Block keys: %s", list(block.keys()) if isinstance(block, dict) else "N/A")
        if isinstance(block, dict):
            for key, value in block.items():
                if isinstance(value, str):
                    logger.info("  block['%s'] = %s... (%d chars)", key, value[:100], len(value))
                else:
                    logger.info("  block['%s'] = %s", key, type(value))
        logger.info("All data keys: %s", list(data.keys()))
        logger.info("=" * 80)

        block_type = block.get("type", "text") if isinstance(block, dict) else "text"
        text = ""
        thinking = ""
        if isinstance(block, dict):
            # Extract both text and thinking content from the block
            text = block.get("text", "")
            thinking = block.get("thinking", "")

        # Combine text and thinking for display - PREFER thinking if available
        full_content = thinking if thinking else text

        # Also extract usage info if present
        usage = data.get("usage", {})
        return {
            "event": "content_block:end",
            "data": {
                "block_type": block_type,
                "block_index": data.get("block_index", 0),
                "text_preview": str(full_content)[:3000] if full_content else "",
                "full_text": str(full_content) if full_content else "",
                "text_length": len(str(full_content)) if full_content else 0,
                "has_thinking": bool(thinking),
                "input_tokens": usage.get("input_tokens") if usage else None,
                "output_tokens": usage.get("output_tokens") if usage else None,
            },
        }

    if event == "provider:request":
        # Debug: log what we're receiving
        logger.debug("provider:request data keys: %s", list(data.keys()))
        logger.debug("provider:request data.model: %s", data.get("model", "NOT_FOUND"))

        # Extract model from top-level or request object
        model = data.get("model", "")
        if not model and "request" in data:
            # Fallback: check request object
            req = data["request"]
            model = getattr(req, "model", "") if hasattr(req, "model") else ""

        return {
            "event": "provider:request",
            "data": {
                "provider": data.get("provider", ""),
                "model": model,
            },
        }

    if event == "provider:response":
        usage = data.get("usage", {})

        # Debug: log what we're receiving
        logger.debug("provider:response data keys: %s", list(data.keys()))
        logger.debug("provider:response has response obj: %s", "response" in data)

        # Extract model from response object (orchestrator contract location)
        model = data.get("model", "")
        if not model and "response" in data:
            resp = data["response"]
            model = getattr(resp, "model", "") if hasattr(resp, "model") else ""

        return {
            "event": "provider:response",
            "data": {
                "provider": data.get("provider", ""),
                "model": model,
                "input_tokens": usage.get("input_tokens") if isinstance(usage, dict) else None,
                "output_tokens": usage.get("output_tokens") if isinstance(usage, dict) else None,
            },
        }

    if event == "execution:start":
        return {
            "event": "execution:start",
            "data": {"message": "Agent reasoning started"},
        }

    if event == "execution:end":
        return {
            "event": "execution:end",
            "data": {"message": "Agent reasoning complete"},
        }

    if event == "orchestrator:complete":
        return {
            "event": "orchestrator:complete",
            "data": {
                "status": data.get("status", ""),
                "turn_count": data.get("turn_count"),
            },
        }

    if event == "prompt:submit":
        return {
            "event": "prompt:submit",
            "data": {"prompt_length": len(data.get("prompt", ""))},
        }

    if event == "session:fork":
        return {
            "event": "session:fork",
            "data": {"child_id": data.get("session_id", "")[:12]},
        }

    # Skip session:start/session:end - not interesting for the UI
    return None


def format_sse(event_data: dict[str, Any]) -> str:
    """Format an event dict as an SSE message string."""
    event_name = event_data.get("event", "message")
    data = json.dumps(event_data.get("data", {}))
    return f"event: {event_name}\ndata: {data}\n\n"
