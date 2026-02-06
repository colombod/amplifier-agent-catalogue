# Skill: Comparison Methodology

Systematic approach for comparing two AI agents to determine overlap, differences, and recommendations.

## Comparison Framework

### Step 1: Identity Comparison

Compare the core identity of both agents:

| Dimension | Questions |
|-----------|-----------|
| Role | Are they the same type of agent? |
| Mission | Do they serve the same purpose? |
| Domain | Do they operate in the same space? |

**Verdicts:**
- **Same role**: Potential duplicate or variant
- **Similar role**: May overlap in some areas
- **Different role**: Likely complementary

### Step 2: Trigger Analysis

Compare when each agent would be invoked:

**Competing Triggers**: Situations where BOTH agents match
- These create user confusion
- Need disambiguation rules

**Exclusive Triggers**: Situations where only ONE matches
- Define clear boundaries
- Show complementary coverage

**Analysis Questions:**
1. Given scenario X, which agent(s) would be invoked?
2. Are there ambiguous scenarios?
3. Can triggers be disambiguated?

### Step 3: Capability Diff

Create a three-way comparison:

```
┌─────────────────┬─────────────────┬─────────────────┐
│  Agent A Only   │     Shared      │  Agent B Only   │
├─────────────────┼─────────────────┼─────────────────┤
│ Capabilities    │ Capabilities    │ Capabilities    │
│ only A has      │ both have       │ only B has      │
└─────────────────┴─────────────────┴─────────────────┘
```

**For shared capabilities**, note:
- Same approach or different?
- Same tools or different?
- Same quality/depth?

### Step 4: Tool Comparison

Tools indicate implementation approach:

**Shared Tools**: Similar implementation
**Different Tools, Same Purpose**: Alternative approaches
**Unique Tools**: Unique capabilities

### Step 5: Constraint Analysis

Compare what each agent WON'T do:

- Do they have compatible boundaries?
- Do they defer to each other?
- Are there gaps between their constraints?

### Step 6: Output Comparison

Compare what each produces:

- Same output types?
- Same quality expectations?
- Compatible or conflicting formats?

## Verdict Categories

### DUPLICATE
**Criteria:**
- Same role and mission
- >80% trigger overlap
- >80% capability overlap
- Same or equivalent tools

**Recommendation:** Keep one, archive the other

### VARIANT
**Criteria:**
- Same role
- Similar triggers
- Different approach to same problem
- Different tools for same purpose

**Recommendation:** Choose preferred variant or document when to use each

### COMPLEMENTARY
**Criteria:**
- Related domain
- Non-competing triggers
- Different capabilities that work together
- May share some tools

**Recommendation:** Keep both, document handoff patterns

### ALTERNATIVE
**Criteria:**
- Same problem space
- Overlapping triggers
- Fundamentally different approach
- Different philosophy/methodology

**Recommendation:** Keep both if approaches serve different needs

### DISTINCT
**Criteria:**
- Different domains
- Non-overlapping triggers
- Different capabilities
- Different outputs

**Recommendation:** No conflict, keep both

## Overlap Calculation

### Capability Overlap
```
shared_caps = caps_a ∩ caps_b
overlap_ratio = |shared_caps| / |caps_a ∪ caps_b|
```

### Trigger Overlap
Estimate based on scenario analysis:
- List 10 common scenarios for domain
- Count how many trigger both agents
- overlap = both_triggered / total_scenarios

### Overall Similarity
```
similarity = (
    0.3 × trigger_overlap +
    0.4 × capability_overlap +
    0.2 × tool_overlap +
    0.1 × output_overlap
)
```

## Generating Recommendations

### If DUPLICATE or high overlap (>80%)
```
Action: REJECT or MERGE
Reasoning: Explain redundancy
Guidance: Which to keep and why
```

### If VARIANT (60-80% overlap)
```
Action: KEEP_BOTH or REPLACE
Reasoning: Explain differences
Guidance: When to use each, or why one is better
```

### If COMPLEMENTARY (30-60% overlap)
```
Action: KEEP_BOTH
Reasoning: Explain complementary nature
Guidance: How they work together, handoff patterns
```

### If DISTINCT (<30% overlap)
```
Action: KEEP_BOTH
Reasoning: No meaningful overlap
Guidance: None needed
```

## Diff Narrative Structure

When explaining comparison results:

1. **Lead with verdict**: "These agents are [VERDICT]"
2. **Explain the key overlap**: What they share
3. **Highlight key differences**: What's unique to each
4. **Provide recommendation**: Clear action to take
5. **Give disambiguation guidance**: If keeping both, how to choose

## Example Comparison Output

```markdown
## Verdict: COMPLEMENTARY

**Bug Hunter** and **Debug Expert** address related problems but with
different specializations.

### What They Share
- Both analyze error messages and stack traces
- Both use systematic debugging approaches
- Both produce fix recommendations

### Key Differences
| Aspect | Bug Hunter | Debug Expert |
|--------|------------|--------------|
| Focus | General bugs | Async/perf issues |
| Approach | Hypothesis-driven | Trace-driven |
| Tools | LSP, grep | Profiler, flamegraph |

### Recommendation: KEEP BOTH

Use **Bug Hunter** for general debugging and code navigation.
Use **Debug Expert** for async race conditions and performance issues.

### Disambiguation
- Error mentions "async", "race", "deadlock" → Debug Expert
- Error mentions "TypeError", "undefined" → Bug Hunter
- Performance issues → Debug Expert
- Logic errors → Bug Hunter
```
