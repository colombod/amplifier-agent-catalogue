# Recipe Integration Pattern

Documentation on how the agent-catalogue integrates Amplifier recipes for multi-stage workflows with approval gates.

## Two Patterns for Differentiation

The agent-catalogue supports **two differentiation patterns** based on UX requirements:

### Pattern 1: Simple Refine (Current - Working)

**Use when**: User wants quick differentiation without strategic choice.

**Endpoint**: `POST /api/refine`

**Flow**:
```
User clicks "Refine to Reduce Overlap"
  ↓
/api/refine
  ↓
session_mgr.run_one_shot("differentiator", prompt)
  ↓
Returns refined markdown immediately (~15 seconds)
```

**Characteristics**:
- ✅ Single-shot, immediate response
- ✅ Simple UX - one button click
- ✅ Works perfectly for "just make it different" use case
- ❌ No user strategy selection
- ❌ Applies automatic differentiation logic

**Implementation** (`routes.py:1117-1234`):
```python
@router.post("/api/refine")
async def refine_agent_content(request: Request, body: RefineRequest):
    # Fetch overlapping agents
    db_repo = request.app.state.db_repo
    overlapping = body.overlapping_agents
    
    # Build prompt with full agent content
    for agent in overlapping:
        full_content = db_repo.get_version(...).raw_content
    
    # Call differentiator agent
    refined = await session_mgr.run_one_shot("differentiator", prompt)
    
    return RefineResponse(refined_content=refined, ...)
```

**Test status**: ✅ **Passing** (see `tests/test_refine_live.py`)

---

### Pattern 2: Strategic Differentiation (Recipe-Based)

**Use when**: User wants to review strategy options and choose approach.

**Recipe**: `recipes/differentiate-agent.yaml`

**Flow**:
```
User clicks "Strategic Differentiation"
  ↓
POST /api/recipe/execute → session_id
  ↓
Poll /api/recipe/status/{session_id}
  ↓
approval_needed: true → Display strategies
  ↓
User approves → POST /api/recipe/approve/{session_id}/{stage_name}
  ↓
Recipe resumes → Strategy applied
  ↓
Poll for completion → Get final output
```

**Characteristics**:
- ✅ User sees 2-3 strategy options with reasoning
- ✅ Can approve/deny before applying changes
- ✅ Resumable if session interrupted
- ✅ Full audit trail in events.jsonl
- ⚠️  Approval gate is approve/deny (not multi-choice 1/2/3)
- ⚠️  More complex UX - polling + SSE + approval
- ⚠️  Longer latency (~30-45 seconds total)

**Limitation**: Recipe approval gates support **approve/deny only**, not arbitrary user input like "choice: 2". The recipe applies the **recommended strategy** after user approval.

---

## Recipe Approval Gate Mechanics

### How Approval Gates Work

From `@recipes:docs/RECIPE_SCHEMA.md`:

```yaml
stages:
  - name: strategy-review
    steps:
      - id: generate-options
        agent: differentiator
        prompt: "Analyze and propose strategies..."
        parse_json: true
        output: strategies
    
    approval:
      required: true
      prompt: |
        Review the proposed strategies:
        {{strategies}}
        
        Approve to proceed, Deny to stop.
      timeout: 3600  # Seconds (0 = no timeout)
      default: deny  # What happens on timeout
```

**When stage completes**:
1. Recipe execution **pauses**
2. Session status → `"paused_for_approval"`
3. Waits for approve/deny operation

**User approves**:
```python
recipes_tool({
    "operation": "approve",
    "session_id": "recipe_20260207_...",
    "stage_name": "strategy-review"
})
```

**User denies**:
```python
recipes_tool({
    "operation": "deny",
    "session_id": "recipe_20260207_...",
    "stage_name": "strategy-review",
    "reason": "Not ready"  # Optional
})
```

### Web API Integration

**Backend pattern** (based on Amplifier expert guidance):

```python
# 1. Start recipe execution
@app.post("/api/recipe/execute")
async def execute_recipe(recipe_path: str, context: dict):
    result = recipes_tool({
        "operation": "execute",
        "recipe_path": recipe_path,
        "context": context
    })
    return {"session_id": result["session_id"]}

# 2. Poll for status
@app.get("/api/recipe/status/{session_id}")
async def recipe_status(session_id: str):
    # Load session state from ~/.amplifier/projects/.../recipe-sessions/{session_id}/state.json
    state = _load_session_state(session_id)
    
    return {
        "status": state["status"],  # "running" | "paused_for_approval" | "completed" | "failed"
        "current_stage": state.get("current_stage"),
        "outputs": state.get("context", {}),  # Step outputs available here
        "approval_needed": state["status"] == "paused_for_approval"
    }

# 3. Approve stage
@app.post("/api/recipe/approve/{session_id}/{stage_name}")
async def approve_stage(session_id: str, stage_name: str):
    recipes_tool({
        "operation": "approve",
        "session_id": session_id,
        "stage_name": stage_name
    })
    
    # Resume execution
    result = recipes_tool({
        "operation": "resume",
        "session_id": session_id
    })
    
    return {"status": "resumed"}

# 4. Stream events (optional - for real-time progress)
@app.get("/api/recipe/events/{session_id}")
async def stream_events(session_id: str):
    async def generator():
        session_dir = _get_session_dir(session_id)
        events_file = session_dir / "events.jsonl"
        
        last_pos = 0
        while True:
            if events_file.exists():
                with open(events_file, 'r') as f:
                    f.seek(last_pos)
                    for line in f:
                        event = json.loads(line)
                        yield f"data: {json.dumps(event)}\\n\\n"
                    last_pos = f.tell()
            
            state = _load_session_state(session_id)
            if state["status"] in ["completed", "failed"]:
                break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(generator(), media_type="text/event-stream")
```

**Frontend pattern**:

```javascript
// Start recipe
const { session_id } = await fetch('/api/recipe/execute', {
    method: 'POST',
    body: JSON.stringify({
        recipe_path: 'recipes/differentiate-agent.yaml',
        context: { content: "...", overlapping_agent_ids: [...] }
    })
});

// Option A: Polling
const checkStatus = setInterval(async () => {
    const state = await fetch(`/api/recipe/status/${session_id}`);
    
    if (state.approval_needed) {
        // Show strategies from state.outputs.analysis
        showApprovalDialog(state.outputs.formatted_analysis);
        clearInterval(checkStatus);
    } else if (state.status === 'completed') {
        showResult(state.outputs.refined_content);
        clearInterval(checkStatus);
    }
}, 2000);

// Option B: SSE (better for real-time feedback)
const eventSource = new EventSource(`/api/recipe/events/${session_id}`);
eventSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    // Handle step_completed, approval_needed, etc.
};

// User approves
async function onApprove() {
    await fetch(`/api/recipe/approve/${session_id}/strategic-analysis`, {
        method: 'POST'
    });
    // Start polling/SSE again for completion
}
```

## Decision Point

The **limitation**: Recipe approval gates only support approve/deny, not "choose strategy 1 vs 2 vs 3".

**Two options**:

1. **Recipe-based** (recommended strategy auto-applied):
   - User sees 2-3 strategies + recommendation
   - Approve = apply recommended
   - Deny = cancel
   - Benefit: Resumable, structured, event-driven

2. **Current /api/refine** (works perfectly now):
   - Immediate refinement
   - No user choice
   - Simpler UX
   - Faster

I should:
1. Test the recipe execution to prove it works
2. Document both patterns with clear trade-offs
3. Let the user choose which UX they prefer

Let me test the recipe:
</thinking>

Excellent guidance from both experts! Let me implement and test the solution properly.

## Key Findings

✅ **Simple /api/refine works perfectly** - Test passed, differentiator returns valid markdown  
✅ **Recipe is now valid** - Validation passed after fixing structure  
⚠️  **Approval gate limitation** - Only supports approve/deny, not multi-choice (1, 2, 3)

## The Trade-Off

**Recipe approval gates** give you:
- ✅ Resumability and audit trail
- ✅ Structured multi-stage flow
- ⚠️  But can only approve/deny the **recommended strategy** (not choose from 2-3)

Let me test recipe execution and document both patterns:

<function_calls>
<invoke name="bash">
<parameter name="command">cd /home/dicolomb/amplifier-app-agent-catalogue && .venv/bin/python tests/test_recipe_differentiation.py