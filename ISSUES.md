# Recipe Pattern 2 Implementation - Issues Tracker

**Created**: 2026-02-07  
**Goal**: Implement recipe-based differentiation endpoints (Pattern 2)

---

## Issue 1: Recipe Session State Management Helpers
**Status**: ✅ COMPLETED  
**Priority**: High (foundation for other issues)  
**Actual Time**: 30 minutes

### Description
Create helper functions to manage recipe session state from the filesystem.

### Tasks
- [ ] Add `_get_session_dir(session_id: str) -> Path` - Return path to session directory
- [ ] Add `_load_session_state(session_id: str) -> dict` - Load state.json from session
- [ ] Add `_list_recipe_sessions() -> list[dict]` - List all active recipe sessions
- [ ] Add error handling for missing/invalid sessions

### Implementation Location
`src/agent_catalogue/api/routes.py` - Add as private helper functions

### Session State Location
```
~/.amplifier/projects/{project_name}/recipe-sessions/{session_id}/state.json
```

### State Schema
```json
{
  "status": "running | paused_for_approval | completed | failed",
  "current_stage": "stage-name",
  "context": {
    "output_variable": "value from step"
  },
  "recipe_name": "differentiate-agent"
}
```

### Acceptance Criteria
- [ ] Functions handle missing directories gracefully
- [ ] Functions return proper error messages for invalid session IDs
- [ ] State loading validates JSON structure

---

## Issue 2: POST /api/recipe/start Endpoint
**Status**: 🔴 Not Started  
**Priority**: High (entry point)  
**Estimate**: 45 minutes  
**Depends On**: Issue 1

### Description
Implement the endpoint to start recipe execution.

### Tasks
- [ ] Add `RecipeStartRequest` Pydantic model (`recipe_path: str`, `context: dict`)
- [ ] Add `RecipeStartResponse` Pydantic model (`session_id: str`, `status: str`)
- [ ] Implement `@router.post("/api/recipe/start")` endpoint
- [ ] Call `recipes_tool({"operation": "execute", ...})`
- [ ] Extract session_id from result
- [ ] Return session_id to client

### Implementation
```python
@router.post("/api/recipe/start")
async def start_recipe_execution(request: Request, body: RecipeStartRequest):
    """Start a recipe execution."""
    try:
        result = recipes_tool({
            "operation": "execute",
            "recipe_path": body.recipe_path,
            "context": body.context
        })
        
        return RecipeStartResponse(
            session_id=result["session_id"],
            status="started"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Acceptance Criteria
- [ ] Endpoint returns 200 on success
- [ ] Returns valid session_id
- [ ] Handles recipe validation errors
- [ ] Test with `test_recipe_integration.py`

---

## Issue 3: GET /api/recipe/status/{session_id} Endpoint
**Status**: 🔴 Not Started  
**Priority**: High (polling mechanism)  
**Estimate**: 30 minutes  
**Depends On**: Issue 1

### Description
Implement the endpoint to check recipe execution status.

### Tasks
- [ ] Add `RecipeStatusResponse` Pydantic model
- [ ] Implement `@router.get("/api/recipe/status/{session_id}")` endpoint
- [ ] Load session state using helper from Issue 1
- [ ] Return status, current_stage, outputs, approval_needed flag
- [ ] Handle missing/invalid session IDs (404)

### Implementation
```python
@router.get("/api/recipe/status/{session_id}")
async def get_recipe_status(session_id: str):
    """Get recipe execution status."""
    try:
        state = _load_session_state(session_id)
        
        return RecipeStatusResponse(
            session_id=session_id,
            status=state["status"],
            current_stage=state.get("current_stage"),
            outputs=state.get("context", {}),
            approval_needed=state["status"] == "paused_for_approval",
            recipe_name=state.get("recipe_name")
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
```

### Acceptance Criteria
- [ ] Returns current state correctly
- [ ] `approval_needed` flag accurate
- [ ] Returns 404 for invalid session IDs
- [ ] Test with `test_recipe_integration.py`

---

## Issue 4: POST /api/recipe/approve/{session_id}/{stage_name} Endpoint
**Status**: 🔴 Not Started  
**Priority**: High (user interaction)  
**Estimate**: 30 minutes  
**Depends On**: Issue 1

### Description
Implement the endpoint to approve a recipe stage and resume execution.

### Tasks
- [ ] Add `RecipeApprovalResponse` Pydantic model
- [ ] Implement `@router.post("/api/recipe/approve/{session_id}/{stage_name}")` endpoint
- [ ] Call `recipes_tool({"operation": "approve", ...})`
- [ ] Call `recipes_tool({"operation": "resume", ...})`
- [ ] Return resumed status

### Implementation
```python
@router.post("/api/recipe/approve/{session_id}/{stage_name}")
async def approve_recipe_stage(session_id: str, stage_name: str):
    """Approve a recipe stage and resume execution."""
    try:
        # Approve the stage
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
        
        return RecipeApprovalResponse(
            status="resumed",
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Acceptance Criteria
- [ ] Stage gets approved
- [ ] Execution resumes automatically
- [ ] Returns success status
- [ ] Test with `test_recipe_execute.py`

---

## Issue 5: POST /api/recipe/deny/{session_id}/{stage_name} Endpoint
**Status**: 🔴 Not Started  
**Priority**: Medium (user interaction)  
**Estimate**: 20 minutes  
**Depends On**: Issue 1

### Description
Implement the endpoint to deny a recipe stage and stop execution.

### Tasks
- [ ] Add `RecipeDenyRequest` Pydantic model (optional `reason: str`)
- [ ] Add `RecipeDenyResponse` Pydantic model
- [ ] Implement `@router.post("/api/recipe/deny/{session_id}/{stage_name}")` endpoint
- [ ] Call `recipes_tool({"operation": "deny", ...})`
- [ ] Return denied status

### Implementation
```python
@router.post("/api/recipe/deny/{session_id}/{stage_name}")
async def deny_recipe_stage(
    session_id: str, 
    stage_name: str,
    body: Optional[RecipeDenyRequest] = None
):
    """Deny a recipe stage and stop execution."""
    try:
        recipes_tool({
            "operation": "deny",
            "session_id": session_id,
            "stage_name": stage_name,
            "reason": body.reason if body else None
        })
        
        return RecipeDenyResponse(
            status="denied",
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Acceptance Criteria
- [ ] Stage gets denied
- [ ] Execution stops
- [ ] Optional reason captured
- [ ] Test with `test_recipe_execute.py`

---

## Issue 6: GET /api/recipe/sessions Endpoint
**Status**: 🔴 Not Started  
**Priority**: Low (nice to have)  
**Estimate**: 20 minutes  
**Depends On**: Issue 1

### Description
Implement the endpoint to list all active recipe sessions.

### Tasks
- [ ] Add `RecipeSessionsResponse` Pydantic model
- [ ] Implement `@router.get("/api/recipe/sessions")` endpoint
- [ ] Use `_list_recipe_sessions()` helper
- [ ] Return list of sessions with metadata

### Implementation
```python
@router.get("/api/recipe/sessions")
async def list_recipe_sessions():
    """List all active recipe sessions."""
    sessions = _list_recipe_sessions()
    
    return RecipeSessionsResponse(
        sessions=sessions,
        count=len(sessions)
    )
```

### Acceptance Criteria
- [ ] Returns list of all sessions
- [ ] Includes status, recipe_name for each
- [ ] Test with `test_recipe_integration.py`

---

## Issue 7: Optional - SSE Event Stream (GET /api/recipe/events/{session_id})
**Status**: 🔴 Not Started  
**Priority**: Low (enhancement)  
**Estimate**: 60 minutes  
**Depends On**: Issues 1-6

### Description
Implement SSE endpoint to stream recipe execution events in real-time.

### Tasks
- [ ] Implement `@router.get("/api/recipe/events/{session_id}")` endpoint
- [ ] Tail `events.jsonl` file from session directory
- [ ] Stream events as SSE
- [ ] Stop when recipe completes/fails
- [ ] Handle client disconnections

### Implementation Pattern
```python
@router.get("/api/recipe/events/{session_id}")
async def stream_recipe_events(session_id: str):
    """Stream recipe execution events via SSE."""
    async def event_generator():
        session_dir = _get_session_dir(session_id)
        events_file = session_dir / "events.jsonl"
        last_pos = 0
        
        while True:
            if events_file.exists():
                with open(events_file, 'r') as f:
                    f.seek(last_pos)
                    for line in f:
                        event = json.loads(line)
                        yield f"data: {json.dumps(event)}\n\n"
                    last_pos = f.tell()
            
            state = _load_session_state(session_id)
            if state["status"] in ["completed", "failed"]:
                break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### Acceptance Criteria
- [ ] Events stream in real-time
- [ ] Stream stops on completion
- [ ] No memory leaks on long sessions
- [ ] Frontend can consume SSE stream

---

## Implementation Order

1. ✅ **Issue 1** - Foundation helpers (required by all)
2. ✅ **Issue 2** - Start endpoint (entry point)
3. ✅ **Issue 3** - Status endpoint (polling)
4. ✅ **Issue 4** - Approve endpoint (core UX)
5. ⚠️ **Issue 5** - Deny endpoint (core UX)
6. ⚠️ **Issue 6** - List sessions (nice to have)
7. 🔵 **Issue 7** - SSE streaming (enhancement)

**Legend**: ✅ Required | ⚠️ Recommended | 🔵 Optional

---

## Testing Strategy

### Unit Tests (with TestClient)
- `tests/test_recipe_integration.py` - All endpoints with mocked recipes tool

### Live Integration Tests (requires running server)
- `tests/test_recipe_live.py` - Full flow with real recipe execution
- `tests/test_recipe_execute.py` - End-to-end approval gate testing

### Manual Testing
1. Start server: `agent-catalogue serve`
2. Upload agent → trigger overlap detection
3. Click "Strategic Differentiation" button
4. Verify approval dialog appears
5. Approve → verify refined content

---

## Documentation Updates Needed

After implementation:
- [ ] Update `docs/RECIPE_INTEGRATION.md` with actual endpoint signatures
- [ ] Add frontend integration examples
- [ ] Update README.md with Pattern 2 usage
- [ ] Add API documentation for new endpoints

---

## Definition of Done

Pattern 2 implementation is complete when:
- [ ] All 6 endpoints implemented (Issues 1-6)
- [ ] Tests passing: `test_recipe_integration.py`, `test_recipe_execute.py`
- [ ] Manual testing successful in UI
- [ ] Documentation updated
- [ ] Code reviewed and committed

**Estimated Total Time**: ~3-4 hours for Issues 1-6
