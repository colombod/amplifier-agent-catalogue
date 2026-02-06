"""SSE Bridge: forwards Amplifier kernel events to web clients via asyncio queues.

Registers as a hook handler on AmplifierSession, capturing streaming events
(content deltas, tool invocations, session forks) and routing them to
per-workflow asyncio.Queue instances for consumption by FastAPI SSE endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from amplifier_core.models import HookResult

logger = logging.getLogger(__name__)

# Events we forward to the web UI
STREAMED_EVENTS = frozenset(
    [
        "content_block:start",
        "content_block:delta",
        "content_block:end",
        "thinking:delta",
        "thinking:final",
        "tool:pre",
        "tool:post",
        "tool:error",
        "session:fork",
        "session:start",
        "session:end",
        "orchestrator:complete",
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

        async def handler(event: str, data: dict[str, Any]) -> HookResult:
            # Route child events to the parent workflow queue
            target = data.get("parent_id") or data.get("session_id") or workflow_id
            # Fall back to the workflow_id if neither matches a known queue
            if target not in self._queues:
                target = workflow_id
            queue = self._queues.get(target)
            if queue:
                try:
                    serialized = _serialize_event(event, data)
                    await queue.put(serialized)
                except Exception:
                    logger.debug("Failed to serialize event %s", event, exc_info=True)
            return HookResult(action="continue")

        for evt in STREAMED_EVENTS:
            try:
                unreg = session.coordinator.hooks.register(
                    evt, handler, name=f"sse_{evt}", priority=900
                )
                unregisters.append(unreg)
            except Exception:
                logger.debug("Could not register hook for %s", evt, exc_info=True)

        return unregisters


def _serialize_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Extract UI-relevant fields from kernel event data."""
    result: dict[str, Any] = {"event": event}

    if event == "content_block:delta":
        result["data"] = {
            "text": data.get("text", ""),
            "block_type": data.get("block_type", "text"),
        }
    elif event == "content_block:start":
        result["data"] = {
            "block_type": data.get("block_type", "text"),
            "index": data.get("index"),
        }
    elif event == "content_block:end":
        result["data"] = {"index": data.get("index")}
    elif event in ("thinking:delta", "thinking:final"):
        result["data"] = {"text": data.get("text", "")}
    elif event == "tool:pre":
        result["data"] = {
            "tool_name": data.get("tool_name", ""),
            "input_preview": str(data.get("tool_input", ""))[:500],
        }
    elif event == "tool:post":
        tool_result = data.get("tool_result", {})
        output = tool_result.get("output", "") if isinstance(tool_result, dict) else ""
        result["data"] = {
            "tool_name": data.get("tool_name", ""),
            "success": tool_result.get("success", False) if isinstance(tool_result, dict) else False,
            "output_preview": str(output)[:500],
        }
    elif event == "tool:error":
        result["data"] = {
            "tool_name": data.get("tool_name", ""),
            "error": str(data.get("error", ""))[:500],
        }
    elif event == "session:fork":
        result["data"] = {
            "child_session_id": data.get("session_id", ""),
            "parent_id": data.get("parent_id", ""),
        }
    elif event == "orchestrator:complete":
        result["data"] = {
            "turn_count": data.get("turn_count"),
            "status": data.get("status", ""),
        }
    else:
        # Generic: include safe scalar fields only
        result["data"] = {
            k: str(v)[:200]
            for k, v in data.items()
            if k not in ("messages", "request", "response") and isinstance(v, (str, int, float, bool))
        }

    return result


def format_sse(event_data: dict[str, Any]) -> str:
    """Format an event dict as an SSE message string."""
    event_name = event_data.get("event", "message")
    data = json.dumps(event_data.get("data", {}))
    return f"event: {event_name}\ndata: {data}\n\n"
