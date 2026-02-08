# Event Flow Architecture

This document explains how the Agent Catalogue uses Amplifier's event system for real-time UI updates.

**Part of**: [Architecture Documentation](ARCHITECTURE.md) - See that doc for complete system overview

## Overview

The application uses **SSE (Server-Sent Events)** to stream Amplifier kernel events from backend agent sessions to the web frontend, providing real-time visibility into:

- Tool invocations (search_similar, get_agent_content, etc.)
- LLM provider calls (Anthropic API)
- Agent reasoning phases
- Content generation progress

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (JavaScript)                                      │
│  - ActivityFeed component listens to SSE stream             │
│  - Displays real-time agent activity                        │
└────────────────┬────────────────────────────────────────────┘
                 │ SSE stream (HTTP EventSource)
                 ↓
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Streaming Endpoint                                 │
│  - /api/stream/improve, /api/stream/evaluate, etc.          │
│  - Creates asyncio.Queue for events                         │
│  - Registers SSE bridge hooks on session                    │
└────────────────┬────────────────────────────────────────────┘
                 │ asyncio.Queue.put()
                 ↓
┌─────────────────────────────────────────────────────────────┐
│  SSE Bridge (sse_bridge.py)                                 │
│  - Hooks into Amplifier kernel events                       │
│  - Serializes events to UI-friendly format                  │
│  - Routes to workflow-specific queues                       │
└────────────────┬────────────────────────────────────────────┘
                 │ hooks.register()
                 ↓
┌─────────────────────────────────────────────────────────────┐
│  Amplifier Kernel                                           │
│  - Emits events via hooks.emit()                            │
│  - tool:pre, tool:post, content_block:end, etc.             │
│  - loop-streaming orchestrator generates events             │
└─────────────────────────────────────────────────────────────┘
```

## Event Flow: Step by Step

### 1. Streaming Endpoint Setup

When a streaming endpoint (e.g., `/api/stream/improve`) is called:

```python
# routes.py
queue = asyncio.Queue()
session = await session_mgr.create_session()
unregisters = sse_bridge.register_hooks(session, workflow_id, agent_name="improver")
sse_bridge._queues[workflow_id] = queue
```

### 2. Hook Registration

The SSE bridge registers handlers for all kernel events:

```python
# sse_bridge.py
KERNEL_EVENTS = [
    "tool:pre", "tool:post", "tool:error",
    "content_block:start", "content_block:end",
    "execution:start", "execution:end",
    "provider:request", "provider:response",
    "prompt:submit", "orchestrator:complete",
    "session:start", "session:end", "session:fork"
]

for evt in KERNEL_EVENTS:
    session.coordinator.hooks.register(evt, handler, name=f"sse_{evt}", priority=900)
```

### 3. Event Emission

When the Amplifier orchestrator runs:

```python
# In loop-streaming orchestrator
hooks.emit("tool:pre", {
    "tool_name": "search_similar",
    "tool_input": {"query": "...", "limit": 5},
    ...
})

# Tool executes
result = await tool.execute(input)

# Orchestrator emits result
hooks.emit("tool:post", {
    "tool_name": "search_similar",
    "result": result,  # ← This is a ToolResult object
    ...
})
```

### 4. Event Serialization

The SSE bridge transforms kernel events into UI-friendly format:

```python
# sse_bridge.py - _build_event()
if event == "tool:post":
    tool_name = data.get("tool_name")
    tool_result = data.get("result")  # ← Critical: field is "result" not "tool_result"
    
    # ToolResult.success defaults to True, only False if error has content
    has_error = bool(tool_result.get("error"))
    success = tool_result.get("success", True) if not has_error else False
    
    output = tool_result.get("output", {})
    
    # Build informative summary
    if "count" in output and "agents" in output:
        # search_similar result
        count = output["count"]
        summary = f"found {count} agents" if count > 1 else f'found "{output["agents"][0]["name"]}"'
    elif "agent_name" in output and "content" in output:
        # get_agent_content result
        summary = f'"{output["agent_name"]}" ({len(output["content"])} chars)'
    
    return {
        "event": "tool:post",
        "data": {
            "tool_name": tool_name,
            "success": success,
            "output_preview": summary
        }
    }
```

### 5. Queue → SSE Stream

```python
# routes.py
async def event_generator():
    while True:
        item = await queue.get()
        if item is None:
            yield "data: [DONE]\n\n"
            break
        event_type = item.get("event", "message")
        payload = json.dumps(item.get("data", {}))
        yield f"event: {event_type}\ndata: {payload}\n\n"
```

### 6. Frontend Display

```javascript
// activity_feed.html - ActivityFeed class
case 'tool:post': {
    const name = data.tool_name;
    const ok = data.success;
    const preview = data.output_preview;
    
    this._add(ok ? '←' : '✗',
        `${agentLabel}<span class="tool-name">${name}</span> ${ok ? preview : 'failed'}`,
        ok ? 'tool' : 'error');
    break;
}
```

## Key Design Decisions

### Why SSE (Server-Sent Events)?

- **One-way communication**: Server pushes updates to client
- **Built into browsers**: No WebSocket library needed
- **Automatic reconnection**: Browser handles connection drops
- **Simple protocol**: Text-based, easy to debug

### Why asyncio.Queue?

- **Decouples event production from consumption**: Hook handlers don't block on SSE sending
- **Buffering**: Can handle bursts of events
- **Async-native**: Works seamlessly with FastAPI streaming responses

### Critical Implementation Details

#### 1. Field Naming: `result` vs `tool_result`

The orchestrator emits tool results in `data["result"]`, NOT `data["tool_result"]`.

```python
# WRONG (always gets empty {})
tool_result = data.get("tool_result", {})

# CORRECT
tool_result = data.get("result", {})
```

**Why this matters**: The field name mismatch caused all tool outputs to appear empty, showing "0 chars" in the UI despite tools succeeding.

#### 2. Success Detection: Empty Error vs Missing Error

ToolResult includes `error` key even when empty (`error: None`).

```python
# WRONG (treats empty error as failure)
success = tool_result.get("success", True) if "error" not in tool_result else False

# CORRECT (checks if error has content)
has_error = bool(tool_result.get("error"))
success = tool_result.get("success", True) if not has_error else False
```

**Why this matters**: `bool(None)` is `False`, so empty errors are correctly treated as success.

#### 3. Tool Output Structure

Different tools return different output structures:

**search_similar**:
```json
{
  "count": 3,
  "agents": [
    {"id": "...", "name": "Agent Name", "description": "...", ...}
  ]
}
```

**get_agent_content**:
```json
{
  "agent_id": "uuid",
  "agent_name": "Agent Name",
  "version": 1,
  "content": "full AGENTS.md content...",
  "content_hash": "sha256..."
}
```

The SSE bridge detects these patterns and generates informative summaries.

## Workflow: Improvement Flow

### Before Fix

```
User clicks "Improve, Then Store"
  ↓
Frontend: POST /api/stream/improve with {content: "..."}
  ↓
Backend: Runs evaluator AGAIN (wasteful)
  ↓
Backend: Runs improver
  ↓
UI shows: "✗ search_similar failed" (wrong - it succeeded)
           "0 chars" (no output info)
```

### After Fix

```
Step 4: Quality Evaluation
  ↓
evaluator runs → evaluation stored in evaluationData
  ↓
User clicks "Improve, Then Store"
  ↓
Frontend: POST /api/stream/improve with {
  content: "...",
  evaluation: evaluationData  ← Reuse existing evaluation
}
  ↓
Backend: if (provided_evaluation):
           skip evaluator ✓
         improver runs with tools
  ↓
SSE Bridge: Correctly detects success (checks error content, not key existence)
            Uses data["result"] not data["tool_result"]
            Generates informative summaries
  ↓
UI shows: "✓ search_similar found 3 agents" (correct)
          "✓ get_agent_content 'Agent Name' (2387 chars)" (informative)
```

## Event Types Reference

### Kernel Events (from loop-streaming)

| Event | When | Data Fields |
|-------|------|-------------|
| `tool:pre` | Before tool executes | `tool_name`, `tool_input` |
| `tool:post` | After tool completes | `tool_name`, `result` (ToolResult) |
| `tool:error` | Tool throws exception | `tool_name`, `error` |
| `content_block:start` | LLM starts generating | `block_type` (text/thinking) |
| `content_block:end` | LLM finishes block | `block` (full content), `usage` |
| `provider:request` | Before LLM API call | `provider`, `model` |
| `provider:response` | After LLM responds | `provider`, `model`, `usage` |
| `execution:start` | Agent starts reasoning | - |
| `execution:end` | Agent completes | - |
| `prompt:submit` | New user message | `prompt` |
| `orchestrator:complete` | Turn finishes | `status`, `turn_count` |

### Application Events (custom)

| Event | When | Data Fields |
|-------|------|-------------|
| `phase` | Workflow phase transition | `phase`, `message`, `agent_name` |
| `result` | Final result ready | Full response object |
| `error` | Workflow error | `message` |

## Tool Protocol Contract

All tools must implement:

```python
class MyTool:
    @property
    def name(self) -> str:
        return "my_tool"
    
    def get_schema(self) -> dict[str, Any]:
        """JSON schema for tool input."""
        return {"type": "object", "properties": {...}}
    
    @property
    def input_schema(self) -> dict[str, Any]:
        """Backward compatibility property for orchestrators expecting input_schema."""
        return self.get_schema()
    
    async def execute(self, input: dict) -> ToolResult:
        """Execute tool logic."""
        return ToolResult(output={...})
```

**Why both methods**: Different orchestrators expect different APIs. Providing both ensures compatibility.

## Debugging Tips

### Enable Debug Logging

All events are logged to `/tmp/agent-catalogue-debug.log` with DEBUG level detail.

**What to look for**:

```bash
# Check if hooks are registered
grep "SSE BRIDGE: register_hooks" /tmp/agent-catalogue-debug.log

# Check tool execution
grep -A30 "TOOL EXECUTE" /tmp/agent-catalogue-debug.log

# Check event serialization
grep -A20 "tool:post EVENT SERIALIZATION" /tmp/agent-catalogue-debug.log

# Check what's in tool results
grep "output keys:" /tmp/agent-catalogue-debug.log
```

### Common Issues

**Issue**: UI shows "✗ failed" for successful tools
- **Check**: Does `data["result"]` have an `error` key with `None` value?
- **Fix**: Use `bool(tool_result.get("error"))` not `"error" in tool_result`

**Issue**: UI shows "0 chars" for all tools
- **Check**: Are you using `data["tool_result"]` instead of `data["result"]`?
- **Fix**: Change to `data.get("result", {})`

**Issue**: No events in UI at all
- **Check**: Are hooks being registered? Look for "SSE BRIDGE: register_hooks" in logs
- **Check**: Are events being emitted? Look for "Emitting event 'tool:post'" in logs
- **Check**: Is queue routing correct? Workflow IDs must match

## Performance Considerations

### Event Queue Size

Events are queued in memory. For long-running workflows:
- Each event ~500 bytes serialized
- 1000 events ≈ 500KB memory
- Queue clears when SSE connection closes

### SSE Connection Limits

Browsers limit concurrent SSE connections (typically 6 per domain). For multiple simultaneous workflows, consider:
- Connection pooling
- Multiplexing workflows on one SSE stream
- WebSocket upgrade for high-concurrency scenarios

### Hook Overhead

Each event emission calls all registered hooks synchronously. With comprehensive logging:
- ~1-2ms overhead per event
- Not noticeable for typical workflows
- Disable DEBUG logging in production

## Future Enhancements

1. **Event Filtering**: Let frontend request specific event types
2. **Replay Buffer**: Send last N events to late-joining connections
3. **Event Compression**: Batch rapid-fire events (e.g., token deltas)
4. **Workflow Multiplexing**: Multiple workflows on one SSE connection
5. **Event Persistence**: Store events for post-hoc analysis

## Related Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete system architecture
- **[API.md](API.md)** - REST API and streaming endpoints
- **[USER_GUIDE.md](USER_GUIDE.md)** - User workflows and features

## Reference

- **SSE Spec**: [MDN Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- **Amplifier Hooks**: `amplifier-core` hooks API documentation
- **ActivityFeed Component**: `src/agent_catalogue/web/templates/components/activity_feed.html`
