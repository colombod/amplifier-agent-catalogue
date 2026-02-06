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

    def register_hooks(self, session: Any, workflow_id: str) -> list:
        """Register event hooks on an AmplifierSession for SSE forwarding.

        Returns list of unregister callables for cleanup.
        """
        unregisters = []
        registered = []

        async def handler(event: str, data: dict[str, Any]) -> HookResult:
            # Route to the workflow queue
            target = data.get("parent_id") or workflow_id
            if target not in self._queues:
                target = workflow_id
            queue = self._queues.get(target)
            if queue:
                try:
                    serialized = _serialize_event(event, data)
                    if serialized:
                        await queue.put(serialized)
                except Exception:
                    logger.debug("Failed to serialize event %s", event, exc_info=True)
            return HookResult(action="continue")

        for evt in KERNEL_EVENTS:
            try:
                unreg = session.coordinator.hooks.register(
                    evt, handler, name=f"sse_{evt}", priority=900
                )
                unregisters.append(unreg)
                registered.append(evt)
            except Exception:
                logger.debug("Could not register hook for %s", evt, exc_info=True)

        if registered:
            logger.debug("SSE bridge registered %d hooks: %s", len(registered), registered)
        else:
            logger.warning("SSE bridge: no hooks registered!")

        return unregisters


def _serialize_event(event: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract UI-relevant fields from kernel event data.

    Returns None for events that have no useful UI representation.
    """

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
        tool_result = data.get("tool_result", {})
        success = tool_result.get("success", False) if isinstance(tool_result, dict) else False
        output = tool_result.get("output", "") if isinstance(tool_result, dict) else ""
        # Summarize the output
        summary = ""
        if isinstance(output, list):
            summary = f"{len(output)} results"
        elif isinstance(output, dict):
            if "agent_id" in output:
                summary = f"agent {output['agent_id'][:8]}..."
            else:
                summary = f"{len(output)} fields"
        elif isinstance(output, str):
            summary = f"{len(output)} chars"
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
        block_type = block.get("type", "text") if isinstance(block, dict) else "text"
        text = ""
        if isinstance(block, dict):
            # Extract text content from the block
            text = block.get("text", "") or block.get("thinking", "") or ""
        # Also extract usage info if present
        usage = data.get("usage", {})
        return {
            "event": "content_block:end",
            "data": {
                "block_type": block_type,
                "block_index": data.get("block_index", 0),
                "text_preview": str(text)[:500] if text else "",
                "text_length": len(str(text)) if text else 0,
                "input_tokens": usage.get("input_tokens") if usage else None,
                "output_tokens": usage.get("output_tokens") if usage else None,
            },
        }

    if event == "provider:request":
        return {
            "event": "provider:request",
            "data": {
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
            },
        }

    if event == "provider:response":
        usage = data.get("usage", {})
        return {
            "event": "provider:response",
            "data": {
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
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
