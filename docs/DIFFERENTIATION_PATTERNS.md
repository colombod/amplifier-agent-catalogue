# Differentiation Patterns: Simple vs Recipe-Based

Two approaches for reducing agent overlap with trade-offs documented.

## Pattern 1: Simple Refine (Current - Recommended)

**Status**: ✅ **Working** (tested, verified)

**Endpoint**: `POST /api/refine`

**When to use**:
- User wants quick differentiation
- No need for strategy review/selection
- Immediate results preferred
- Simple UX (one button click)

**Flow**:
```
User clicks "Refine to Reduce Overlap"
  ↓
POST /api/refine
  {
    content: "current AGENTS.md",
    overlapping_agents: [{id, name, capabilities, domains, tools}]
  }
  ↓
Backend fetches FULL content of overlapping agents
  ↓
session_mgr.run_one_shot("differentiator", comprehensive_prompt)
  ↓
Returns RefineResponse (~15 seconds)
  {
    refined_content: "improved markdown",
    changes: [diff sections],
    token_metrics: {before, after, delta}
  }
```

**Implementation**: See `src/agent_catalogue/api/routes.py:1117-1234`

**Test**: `tests/test_refine_live.py` ✅ Passes

**Characteristics**:
- **Latency**: ~15 seconds
- **UX**: One-click → immediate result
- **Strategy**: Differentiator applies best judgment automatically
- **Resumable**: No (single-shot session)
- **Event streaming**: No (synchronous response)

---

## Pattern 2: Recipe-Based Strategic Differentiation

**Status**: ✅ **FULLY IMPLEMENTED** (backend + frontend complete as of Feb 2026)

**Recipe**: `recipes/differentiate-agent.yaml`

**When to use**:
- User wants to review differentiation strategies before applying
- Need resumability (can pause/restart)
- Want full audit trail (events.jsonl)
- Multi-stakeholder approval workflow

**Flow**:
```
User clicks "Strategic Differentiation"
  ↓
POST /api/recipe/start
  {
    recipe_path: "recipes/differentiate-agent.yaml",
    context: {content: "...", overlapping_agent_ids: [...]  }
  }
  → Returns {session_id: "recipe_..."}
  ↓
[STAGE 1: Strategic Analysis]
  Step 1: analyze-overlap (differentiator reads competitors, proposes strategies)
  Step 2: format-for-approval (differentiator formats for display)
  ↓
Recipe pauses for approval
  ↓
Frontend polls /api/recipe/status/{session_id}
  → Returns {
      status: "paused_for_approval",
      outputs: {
        analysis: {strategies: [...], recommended_index: 0},
        formatted_analysis: "markdown display"
      }
    }
  ↓
Frontend displays strategies to user
User clicks "Approve" or "Deny"
  ↓
POST /api/recipe/approve/{session_id}/strategic-analysis
  ↓
[STAGE 2: Strategy Application]
  Step: apply-recommended-strategy (applies the recommended strategy)
  ↓
Recipe completes
  ↓
Frontend polls /api/recipe/status/{session_id}
  → Returns {
      status: "completed",
      outputs: {refined_content: "improved markdown"}
    }
```

**Recipe stages**:
1. **strategic-analysis** (2 steps + approval gate)
   - `analyze-overlap`: Differentiator reads competitors, proposes 2-3 strategies (JSON)
   - `format-for-approval`: Format for user review
   - **Approval gate**: User approves recommended strategy or denies
2. **strategy-application** (1 step)
   - `apply-recommended-strategy`: Apply the chosen approach

**Limitation**:
⚠️  **Approval gates only support approve/deny** - user CANNOT select "strategy 2 of 3". The recipe applies the **recommended** strategy after approval.

For multi-choice UX (let user pick strategy 1, 2, or 3), use Pattern 1 with enhanced UI.

**Characteristics**:
- **Latency**: ~30-45 seconds (two LLM phases + user wait)
- **UX**: Multi-step with approval checkpoint
- **Strategy**: User sees options, approves recommended
- **Resumable**: Yes (recipe checkpoints after each step)
- **Event streaming**: Yes (can stream events.jsonl)

**Implementation**:
- ✅ `POST /api/recipe/start` - Start recipe execution
- ✅ `GET /api/recipe/status/{session_id}` - Poll for status + outputs
- ✅ `POST /api/recipe/approve` - User approval/denial
- ✅ `GET /api/recipe/sessions` - List all recipe sessions
- ✅ `GET /api/recipe/approvals` - List pending approvals
- ✅ `POST /api/recipe/cancel/{session_id}` - Cancel execution
- ⏸️ `GET /api/recipe/events/{id}` - SSE event stream (Issue #1, optional enhancement)

**Frontend**:
- ✅ Strategic Differentiation button (shows when duplication >80%)
- ✅ Approval modal with strategy review
- ✅ Polling mechanism for recipe status
- ✅ Approve/deny/close handlers
- ✅ Content update after completion

**Code locations**:
- Backend: `src/agent_catalogue/api/recipes_routes.py` (all endpoints)
- Frontend: `src/agent_catalogue/web/templates/upload.html:1017-2403` (UI integration)
- Tests: `tests/test_recipe_endpoints_quick.py` (verified)

---

## Recommendation

**Start with Pattern 1** (already working):
- Simpler UX, faster results
- User gets refined content immediately
- Can enhance with "Show reasoning" button if needed

**Add Pattern 2 later** if you need:
- Multi-stakeholder approval workflows
- Resumable long-running refinements
- Full audit trail requirements
- Strategic review checkpoints

---

## Implementation Details

### Pattern 1: /api/refine (Current)

**Key implementation details**:

1. **Fetches full overlapping agent content**:
   ```python
   for agent_info in overlapping:
       agent = db_repo.get_agent(agent_info["id"])
       version = db_repo.get_latest_version(agent.id)
       full_content = version.raw_content
   ```

2. **Builds comprehensive prompt**:
   - Current agent content
   - Full text of each overlapping agent (not just summaries)
   - Strategic frameworks from differentiator agent
   - Specific guidance on differentiation approaches

3. **Differentiator agent** (`agents/differentiator.md`):
   - Has 5 positioning frameworks built-in
   - Reads overlapping agents with `get_agent_content` tool
   - Applies strategic differentiation
   - Returns markdown directly

**Test verification**:
```bash
.venv/bin/python tests/test_refine_live.py
# ✓ 200 OK
# ✓ Refined content: 1499 chars
# ✓ Valid markdown structure
```

### Pattern 2: Recipe Execution (To Implement)

**Recipe endpoints** (based on Amplifier expert pattern):

```python
from pathlib import Path
import json

RECIPE_SESSION_DIR = Path.home() / ".amplifier/projects/agent-catalogue/recipe-sessions"

def _load_session_state(session_id: str) -> dict:
    state_file = RECIPE_SESSION_DIR / session_id / "state.json"
    with open(state_file) as f:
        return json.load(f)

@router.post("/api/recipe/differentiate/start")
async def start_differentiation_recipe(request: Request, body: dict):
    \"\"\"Start strategic differentiation recipe.\"\"\"
    result = recipes_tool({
        "operation": "execute",
        "recipe_path": "recipes/differentiate-agent.yaml",
        "context": {
            "content": body["content"],
            "overlapping_agent_ids": body["overlapping_agent_ids"]
        }
    })
    
    return {
        "session_id": result["session_id"],
        "status": result["status"]
    }

@router.get("/api/recipe/status/{session_id}")
async def recipe_status(session_id: str):
    \"\"\"Get recipe status and outputs for polling.\"\"\"
    state = _load_session_state(session_id)
    
    return {
        "status": state["status"],
        "stage": state.get("current_stage"),
        "outputs": state.get("context", {}),
        "approval_needed": state["status"] == "paused_for_approval"
    }

@router.post("/api/recipe/approve/{session_id}/{stage_name}")
async def approve_recipe_stage(session_id: str, stage_name: str):
    \"\"\"User approves stage - recipe continues.\"\"\"
    recipes_tool({
        "operation": "approve",
        "session_id": session_id,
        "stage_name": stage_name
    })
    
    result = recipes_tool({
        "operation": "resume",
        "session_id": session_id
    })
    
    return {"status": "resumed"}
```

**Frontend pattern**:

```javascript
// 1. Start recipe
const { session_id } = await fetch('/api/recipe/differentiate/start', {
    method: 'POST',
    body: JSON.stringify({
        content: currentContent,
        overlapping_agent_ids: overlappingIds
    })
});

// 2. Poll for status
const checkApproval = setInterval(async () => {
    const state = await fetch(`/api/recipe/status/${session_id}`);
    
    if (state.approval_needed) {
        // Display formatted strategies
        showApprovalDialog({
            strategies: state.outputs.formatted_analysis,
            onApprove: async () => {
                await fetch(`/api/recipe/approve/${session_id}/strategic-analysis`, {
                    method: 'POST'
                });
                pollForCompletion(session_id);
            }
        });
        clearInterval(checkApproval);
    }
}, 2000);

function pollForCompletion(session_id) {
    const checkComplete = setInterval(async () => {
        const state = await fetch(`/api/recipe/status/${session_id}`);
        
        if (state.status === 'completed') {
            showResult(state.outputs.refined_content);
            clearInterval(checkComplete);
        }
    }, 2000);
}
```

---

## Testing

### Pattern 1 Tests

**File**: `tests/test_refine_live.py`

```python
def test_refine_endpoint():
    client = TestClient(app)  # Requires live server
    
    response = client.post("/api/refine", json={
        "content": "test agent...",
        "overlapping_agents": [{...}]
    })
    
    assert response.status_code == 200
    assert len(response.json()["refined_content"]) > 100
```

**Status**: ✅ Passing

### Pattern 2 Tests (To Implement)

**File**: `tests/test_recipe_differentiation.py`

```python
def test_recipe_flow():
    # 1. Execute recipe
    result = recipes_tool({
        "operation": "execute",
        "recipe_path": "recipes/differentiate-agent.yaml",
        "context": {...}
    })
    
    session_id = result["session_id"]
    
    # 2. Wait for approval needed
    # (Poll state.json or use session-analyst)
    
    # 3. Approve
    recipes_tool({"operation": "approve", "session_id": session_id, "stage_name": "..."})
    
    # 4. Resume
    recipes_tool({"operation": "resume", "session_id": session_id})
    
    # 5. Verify completion
    state = _load_session_state(session_id)
    assert state["status"] == "completed"
    assert "refined_content" in state["context"]
```

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Differentiator agent | ✅ Working | Applies strategic frameworks |
| /api/refine endpoint | ✅ Working | Test passed, 15s latency |
| differentiate-agent.yaml | ✅ Valid | Staged recipe with approval |
| Recipe endpoints (6 total) | ✅ Implemented | All endpoints tested Feb 2026 |
| Recipe frontend integration | ✅ Implemented | Button, modal, polling (commit c8bb6d1) |
| Recipe backend tests | ✅ Passing | test_recipe_endpoints_quick.py |
| Event streaming (SSE) | ⏸️  Optional enhancement | Issue #1 (non-blocking) |

**Both patterns are production-ready as of February 2026.**
