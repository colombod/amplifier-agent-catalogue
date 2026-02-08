# Agent Catalogue User Guide

Learn how to use Agent Catalogue to manage your AI agent definitions.

## Quick Start

1. **Start the server**: `agent-catalogue serve`
2. **Open browser**: http://localhost:8000
3. **Upload agent**: Click "Upload Agent" and select your AGENTS.md file
4. **Review results**: See metadata extraction, similar agents, quality score
5. **Improve if needed**: Click "Improve" to fix quality issues
6. **Differentiate if needed**: Click "Refine" or "Strategic Differentiation" to reduce overlap
7. **Store**: Save to catalogue for future reference

---

## Upload & Analysis

### What Happens When You Upload

**Step 1: Metadata Extraction**
- Agent name, description, capabilities parsed from markdown
- Domains identified (engineering, product, design, etc.)
- Tools referenced in the agent definition
- Complexity assessed (simple, medium, complex)

**Step 2: Similarity Detection**
- Your agent is compared against all agents in the catalogue
- Embeddings used for semantic similarity (not just keyword matching)
- Top similar agents shown with overlap percentage

**Step 3: Quality Evaluation**
- Grade assigned (A-F scale)
- Issues identified (clarity, specificity, structure)
- Concrete suggestions provided

### Understanding Similarity Scores

| Similarity | Meaning |
|------------|---------|
| **90-100%** | Near duplicate - differentiation critical |
| **80-89%** | High overlap - differentiation recommended |
| **70-79%** | Moderate overlap - consider differentiation |
| **60-69%** | Some overlap - acceptable |
| **<60%** | Distinct positioning - good |

**Red banner appears when similarity >80%** - this triggers differentiation options.

---

## Improving Agent Quality

### When to Use "Improve"

Use when quality evaluation shows issues:
- Grade C or below
- Clarity problems (vague descriptions)
- Missing critical sections
- Inconsistent structure

### What the Improver Does

The improver agent:
1. Identifies specific quality issues
2. Rewrites unclear sections
3. Adds missing information
4. Improves structure and flow
5. **Preserves** your agent's core purpose and identity

### After Improvement

Review the changes:
- **Green sections**: New content added
- **Red sections**: Content removed
- **Yellow sections**: Content modified

Accept or reject the improvements. You can always edit manually.

---

## Reducing Overlap (Differentiation)

When your agent overlaps >80% with existing agents, you have two options:

### Option 1: Simple Refine ✅ (Recommended)

**Best for**: Quick differentiation, trust the AI

**How it works**:
1. Click "Refine to Reduce Overlap" button
2. Wait ~15 seconds
3. Review differentiated version
4. Accept or manually adjust

**What the differentiator does**:
- Reads full content of overlapping agents
- Applies one of 5 strategic frameworks:
  1. **Narrow Scope** - Specialize in subset
  2. **Different Approach** - Same problem, different method
  3. **Adjacent Niche** - Related but distinct
  4. **Unique Combo** - Intersection nobody covers
  5. **Different Audience** - Segment specialization

**Result**: Refined agent with clearer positioning

### Option 2: Strategic Differentiation ✅

**Best for**: Strategic decisions, want to review options

**How it works**:
1. Click "Strategic Differentiation" button (appears when overlap >80%)
2. Wait ~30-60 seconds for strategy generation
3. **Approval modal appears** with 2-3 differentiation strategies
4. Review each strategy's reasoning, changes, outcomes, trade-offs
5. Click "Approve" to apply recommended strategy (or "Deny" to cancel)
6. Wait for application (~30s)
7. Review final differentiated version

**What you see in the approval modal**:
```
Strategic Analysis Complete

Strategy 1: Narrow Scope (Recommended)
Reasoning: Current agent spreads across A, B, C but existing 
agents already cover B and C well. Focusing on A creates clear 
differentiation.

Changes: Remove capabilities [B, C], deepen focus on A

Expected Outcome: Reduces overlap from 85% to ~45%

Trade-offs: No longer serves users needing B or C

---

Strategy 2: Different Approach
...

Approve | Deny | Close
```

**After approval**: Recipe applies the recommended strategy and returns refined content.

**Limitation**: You can only approve or deny the *recommended* strategy (marked in the modal). You cannot pick "Strategy 2 instead of Strategy 1". For that flexibility, use Pattern 1 with multiple iterations.

---

## Searching the Catalogue

### Semantic Search

Use the search box to find agents by:
- Capabilities ("testing", "code review")
- Domains ("Python development", "DevOps")
- Purpose ("debugging", "documentation")

**Search uses embeddings**, not keyword matching - it understands meaning.

**Examples**:
- "help with FastAPI testing" → finds testing specialists
- "improve code quality" → finds reviewers, linters, formatters
- "CI/CD for small teams" → finds DevOps agents focused on simplicity

### Browsing Agents

- **All Agents** page shows complete catalogue
- Filter by domain, complexity, or quality grade
- Sort by similarity to a reference agent
- View version history for evolving agents

---

## Understanding the Workflow

```
Upload AGENTS.md
    ↓
Metadata Extracted + Similarity Detected
    ↓
Quality Evaluated
    ↓
[IF grade < B] → Improve → Review changes
    ↓
[IF overlap > 80%] → Differentiate → Review strategies
    ↓
Store in Catalogue
    ↓
Searchable by others
```

**You can exit at any point** - uploading doesn't automatically store. Review first, then decide.

---

## Best Practices

### Writing Good Agent Definitions

Before uploading, ensure your AGENTS.md has:
- **Clear name**: Descriptive, not generic
- **Specific purpose**: What problem does this solve?
- **Concrete capabilities**: List what it can do
- **Domain context**: Where does this apply?
- **Usage examples**: When to use vs not use
- **Tool requirements**: What tools does it need?

See `context/agent-anatomy.md` for complete guidance.

### Avoiding High Overlap

**Before uploading**, search the catalogue:
1. Search for similar capabilities
2. Review existing agents in your domain
3. Identify gaps or underserved niches
4. Position your agent in those gaps

**Better to differentiate proactively** than reactively after upload.

### Iteration Strategy

If first differentiation doesn't reduce overlap enough:
1. Try the other differentiation pattern
2. Consider combining approaches (narrow scope + different audience)
3. Use the catalogue search to find truly empty positioning
4. Consult the 5 strategic frameworks in the differentiator agent

---

## Troubleshooting

### "No similar agents found"

**Good news**: Your agent is unique! No differentiation needed.

### "Improve didn't help much"

Quality improvement fixes clarity/structure issues, **not overlap**. If the problem is similarity, use **Differentiate** instead.

### "Differentiation made it worse"

Try the other pattern or iterate. Strategic Differentiation (Pattern 2) shows you WHY each approach works - use that insight to manually refine.

### "Strategic Differentiation button not appearing"

Button only appears when **overlap >80%**. If you think there should be high overlap but button doesn't show:
- Check that similar agents were found
- Verify the similarity threshold
- Use Simple Refine instead (always available)

### "Approval modal stuck loading"

Pattern 2 recipe execution can take 30-90 seconds. If stuck longer:
1. Check server logs: `tail -f /tmp/agent-catalogue-debug.log`
2. Verify Anthropic API key is set correctly
3. Check network connectivity

---

## Tips & Tricks

### Quick Workflow
For fast iteration:
1. Upload → Improve → Store (skip differentiation if overlap is low)
2. Total time: ~45 seconds

### Strategic Workflow
For perfect positioning:
1. Upload → Review similar agents → Strategic Differentiation → Review options → Apply
2. Total time: ~2-3 minutes

### Batch Processing
Upload multiple agents, compare them against each other, then differentiate strategically to create a portfolio of complementary specialists.

---

## Next Steps

After storing your agent:
- **Search** to verify it appears correctly
- **Compare** against similar agents to validate positioning
- **Share** the catalogue link with your team
- **Iterate** by uploading new versions as your agent evolves

---

**For API details**: See `docs/API.md`  
**For architecture**: See `docs/ARCHITECTURE.md`  
**For contributing**: See `CONTRIBUTING.md` (when available)
