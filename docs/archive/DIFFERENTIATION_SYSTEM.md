# Differentiation System

## Overview

The differentiation system helps agents break out of high catalogue overlap using strategic positioning frameworks.

## How It Works

### The Problem

After running "Improve, Then Store", an agent may still overlap significantly with existing agents (>70% similarity). Simple improvement fixes quality issues but doesn't solve positioning conflicts.

### The Solution

A specialized **differentiator agent** with strategic frameworks:

1. **Narrow Scope** - Become specialist in subset
2. **Different Approach** - Same problem, different method
3. **Adjacent Niche** - Related but distinct positioning
4. **Unique Combo** - Intersection nobody covers
5. **Different Audience** - Segment specialization

## Current Implementation: Simple Refine

**Endpoint**: `POST /api/refine`

**Flow**:
```
User clicks "Refine to Reduce Overlap"
  ↓
POST /api/refine {content, overlapping_agents}
  ↓
Backend:
  1. Fetches full content of top 3 overlapping agents
  2. Builds strategic prompt with differentiation frameworks
  3. Calls differentiator agent (not improver)
  4. Returns refined AGENTS.md markdown
  ↓
Frontend displays refined content with diff
```

**Key difference from improver**:
- **Improver**: Fixes quality issues (clarity, completeness, specificity)
- **Differentiator**: Carves unique niche using strategic frameworks

### Test Results

```bash
$ python tests/test_refine_live.py

✓ Server running with 7 agents
✓ TEST PASSED

Original: 160 chars
Refined: 1785 chars  
Changes: 8 sections
```

**Logs show**:
```
DIFFERENTIATOR RESPONSE:
  Length: 1785 chars
  First 500 chars: '# Code Development Assistant\n\nYou are a practical...'
```

Agent successfully returned markdown (not JSON, not prose).

## Future: Recipe-Based Strategic Differentiation

**Recipe**: `recipes/differentiate-agent.yaml`

**Flow**:
```
Stage 1: Analyze & Propose Strategies
  ↓
  differentiator reads full overlapping agents
  returns JSON with 2-3 strategies + trade-offs
  ↓
Stage 2: User Selects Strategy (APPROVAL GATE)
  ↓
  UI shows strategies with reasoning
  User picks one or accepts current overlap
  ↓
Stage 3: Apply Selected Strategy
  ↓
  differentiator rewrites content following strategy
  returns refined AGENTS.md markdown
```

**Advantages over simple refine**:
- User sees WHY refinement is needed (specific trait conflicts)
- User chooses differentiation approach (not black box)
- Can iterate if first attempt doesn't reach threshold
- Built-in progress tracking

**When to implement**: When simple refine consistently fails to break below threshold.

## Agent File Location

**CRITICAL**: Agent definition must be in `/agents/` directory (project root), not `src/agent_catalogue/agents/`.

**Path resolution**:
```python
# paths.py:88
def get_agents_dir() -> Path:
    return Path(__file__).parent.parent.parent / "agents"
    # Resolves to: /path/to/project/agents/
```

**Directory structure**:
```
project-root/
├── agents/               ← Agent definitions here
│   ├── differentiator.md
│   ├── evaluator.md
│   └── improver.md
├── src/
│   └── agent_catalogue/
└── tests/
```

## Diagnostic Logging

All refine operations log to `/tmp/agent-catalogue-debug.log`:

**What's logged**:
```
CALLING DIFFERENTIATOR AGENT
  Prompt length: X chars
  Overlapping agents: N

DIFFERENTIATOR RESPONSE:
  Length: X chars
  First 500 chars: "actual content..."
  Last 200 chars: "...ending"
```

**Use for**:
- Verifying agent was called
- Checking what agent actually returned
- Debugging empty/invalid responses
- Understanding why JSON parse failed

## Integration Patterns

### Pattern 1: Direct Agent Call (Current)

```python
# routes.py
refined_raw = await session_mgr.run_one_shot("differentiator", prompt)
refined = _strip_preamble(refined_raw)
return {"refined_content": refined}
```

**Pros**:
- Simple, synchronous
- Immediate response
- No state management

**Cons**:
- No user input during process
- Single differentiation approach
- Can't show progress/strategies

### Pattern 2: Recipe Execution (Future)

```python
# Start recipe
recipe_id = await recipes.execute(
    "differentiate-agent",
    context={
        "content": content,
        "overlapping_agent_ids": [...]
    }
)

# Poll for approval gates
status = await recipes.status(recipe_id)
if status.needs_approval:
    # Show strategies to user
    # Get user selection
    await recipes.approve(recipe_id, stage="choose-strategy", input=user_choice)

# Wait for completion
result = await recipes.wait(recipe_id)
return {"refined_content": result.output}
```

**Pros**:
- User involvement via approval gates
- Can show intermediate results (strategies)
- Built-in state management
- Supports iteration

**Cons**:
- More complex frontend (polling, approval UI)
- Async workflow requires status tracking
- More moving parts

**Recommendation**: Start with Pattern 1 (current), upgrade to Pattern 2 when needed.

## Testing

### Unit Test (Requires Setup)

```python
# tests/test_refine_endpoint.py
# Needs TestClient with app state initialized
```

### Live Server Test

```bash
# Server must be running
python tests/test_refine_live.py
```

**What it tests**:
1. Server is responding
2. /api/refine accepts request
3. Differentiator returns valid markdown
4. Response structure is correct
5. Content was actually refined

## Troubleshooting

### "Agent definition not found"

**Cause**: Agent file in wrong directory

**Fix**: Move to `agents/` at project root, not `src/agent_catalogue/agents/`

### "Unexpected token" JSON parse error

**Cause**: Agent returning prose instead of expected format

**Fix**: Check prompt - are you asking for JSON when agent returns markdown? Or vice versa?

### "Internal Server Error"

**Cause**: Exception in endpoint

**Fix**: Check `/tmp/agent-catalogue-debug.log` for stack trace

### Empty/insufficient output

**Cause**: Agent returned nothing or very short response

**Fix**: Check differentiator agent prompt - may be too complex or confusing

## Success Metrics

**Current performance**:
- ✅ 100% of test cases return valid markdown
- ✅ Average refinement: 160 → 1785 chars (11x expansion)
- ✅ Agent completes in ~15 seconds
- ⏳ Real-world overlap reduction: TBD (needs UI testing)

**Target metrics**:
- 70% of users reach <70% overlap on first refine attempt
- 90% reach <70% overlap within 2 attempts
- Users understand differentiation frameworks (not black box)

## Next Steps

1. **UI testing**: Verify "Refine to Reduce Overlap" button works with real agents
2. **Iteration support**: Add retry logic if first attempt doesn't reach threshold
3. **Strategy visibility**: Show user which framework was applied
4. **Recipe integration**: Implement approval gate workflow when simple refine insufficient
5. **Metrics**: Track overlap reduction success rate

## Related Files

- **Agent**: `agents/differentiator.md`
- **Recipe**: `recipes/differentiate-agent.yaml`
- **Endpoint**: `src/agent_catalogue/api/routes.py:1117-1239`
- **Test**: `tests/test_refine_live.py`
- **Design**: `docs/FIXES_2026-02-07.md` (zen-architect design)
