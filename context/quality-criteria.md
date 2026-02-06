# Skill: Quality Criteria

Evaluation criteria for assessing the quality of AGENTS.md definitions.

## Quality Dimensions

### 1. Clarity (0-10)

**What it measures:** How clearly the agent's purpose and behavior are defined.

**High clarity indicators:**
- Specific, unambiguous language
- Concrete examples provided
- Clear trigger conditions
- Explicit boundaries

**Low clarity indicators:**
- Vague descriptions ("handles various tasks")
- Missing examples
- Ambiguous triggers ("when appropriate")
- Unclear boundaries

**Scoring:**
- 9-10: Crystal clear, no ambiguity
- 7-8: Clear with minor ambiguities
- 5-6: Understandable but vague in places
- 3-4: Significant ambiguity
- 1-2: Unclear purpose

### 2. Completeness (0-10)

**What it measures:** Whether all essential components are present.

**Essential components:**
- [ ] Name/identity
- [ ] Purpose/mission
- [ ] Trigger conditions
- [ ] Capabilities
- [ ] Constraints/limitations
- [ ] Tool usage
- [ ] Output description

**Scoring:**
- 10: All components present and detailed
- 8: All components present, some brief
- 6: Most components present
- 4: Missing several components
- 2: Minimal definition

### 3. Specificity (0-10)

**What it measures:** How specific and actionable the instructions are.

**High specificity indicators:**
- Named tools with usage patterns
- Specific scenarios described
- Concrete output formats
- Step-by-step approaches

**Low specificity indicators:**
- Generic capability lists
- Abstract descriptions
- No tool details
- Vague methodology

**Scoring:**
- 9-10: Highly specific, immediately actionable
- 7-8: Mostly specific with some general areas
- 5-6: Mix of specific and general
- 3-4: Mostly general
- 1-2: Very abstract

### 4. Consistency (0-10)

**What it measures:** Internal consistency of the definition.

**Check for:**
- Capabilities match stated purpose
- Tools match capabilities
- Constraints don't contradict capabilities
- Trigger conditions align with domain

**Issues:**
- Claimed capability without tool support
- Constraint that blocks stated capability
- Trigger that doesn't match domain
- Conflicting instructions

**Scoring:**
- 10: Fully consistent
- 8: Minor inconsistencies
- 6: Some inconsistencies
- 4: Notable contradictions
- 2: Significant contradictions

### 5. Differentiation (0-10)

**What it measures:** How well the agent is differentiated from others.

**Good differentiation:**
- Unique capability combination
- Clear niche
- Explicit "not for" statements
- Handoff patterns defined

**Poor differentiation:**
- Generic capabilities
- Overlaps with common agents
- No boundaries defined
- Could be any agent

**Scoring:**
- 9-10: Highly unique, clear niche
- 7-8: Good differentiation
- 5-6: Some unique aspects
- 3-4: Mostly generic
- 1-2: No differentiation

## Overall Quality Score

```
quality_score = (
    clarity × 0.25 +
    completeness × 0.25 +
    specificity × 0.20 +
    consistency × 0.15 +
    differentiation × 0.15
)
```

**Quality Grades:**
- A (9-10): Excellent - Production ready
- B (7-8.9): Good - Minor improvements possible
- C (5-6.9): Adequate - Needs refinement
- D (3-4.9): Poor - Significant work needed
- F (0-2.9): Failing - Needs rewrite

## Common Quality Issues

### Issue: Vague Triggers
**Problem:** "Use when debugging is needed"
**Better:** "Use when: stack trace present, error message reported, test failing unexpectedly"

### Issue: Capability Without Tools
**Problem:** Lists "code analysis" but no analysis tools mentioned
**Fix:** Add specific tools or remove capability

### Issue: Conflicting Instructions
**Problem:** "Works autonomously" but also "always ask before making changes"
**Fix:** Clarify autonomy level for different scenarios

### Issue: Missing Boundaries
**Problem:** No "limitations" or "does not do" section
**Fix:** Add explicit boundaries to prevent misuse

### Issue: Generic Description
**Problem:** "Helps with coding tasks"
**Better:** "Specializes in Python async debugging using structured logging analysis"

## Quality Improvement Suggestions

### For Low Clarity
1. Add concrete examples
2. Replace vague words with specific ones
3. Define trigger scenarios explicitly
4. Add "for example" sections

### For Low Completeness
1. Add missing sections
2. Expand brief sections
3. Include tool documentation
4. Add output format specifications

### For Low Specificity
1. Name specific tools
2. Describe step-by-step approach
3. Provide example inputs/outputs
4. Detail methodology

### For Low Consistency
1. Audit capabilities vs tools
2. Review constraints vs capabilities
3. Align triggers with domain
4. Remove contradictions

### For Low Differentiation
1. Identify unique value
2. Add "not for" statements
3. Define handoff patterns
4. Narrow scope if too broad

## Automated Checks

### Structural Checks
- [ ] Has H1 title
- [ ] Has purpose section
- [ ] Has capabilities section
- [ ] Has constraints section
- [ ] Has tool references

### Content Checks
- [ ] No vague keywords ("various", "appropriate", "etc")
- [ ] Tool names are specific
- [ ] Examples provided
- [ ] Word count > 200

### Consistency Checks
- [ ] All mentioned tools exist
- [ ] Capabilities match domain
- [ ] No contradictory statements
