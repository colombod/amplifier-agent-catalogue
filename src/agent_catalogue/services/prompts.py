"""LLM prompts for agent behavioral analysis and comparison."""

# =============================================================================
# BEHAVIOR EXTRACTION PROMPT
# =============================================================================
# Extracts structured behavioral traits from an agent's raw content

BEHAVIOR_EXTRACTION_PROMPT = """
Analyze this AGENTS.md file and extract a structured behavioral profile.

<agent_content>
{content}
</agent_content>

Extract the following behavioral dimensions.
For each, provide specific, concrete behaviors (not vague descriptions).

## Output Format (JSON)

```json
{{
  "core_identity": {{
    "primary_role": "One sentence: what this agent fundamentally IS",
    "mission": "What it's trying to accomplish for users"
  }},
  "triggers": {{
    "when_to_use": ["Specific situations that should invoke this agent"],
    "input_types": ["Types of inputs/requests it handles"],
    "keywords": ["Words/phrases that suggest this agent"]
  }},
  "capabilities": {{
    "can_do": ["Specific actions it CAN perform"],
    "approach": ["HOW it approaches problems - methodology"],
    "tools_used": ["Tools/commands it employs"]
  }},
  "constraints": {{
    "cannot_do": ["Explicit limitations"],
    "defers_to": ["Other agents/systems it hands off to"],
    "boundaries": ["Scope boundaries it respects"]
  }},
  "interaction_style": {{
    "communication": "How it communicates with users",
    "autonomy_level": "autonomous | guided | collaborative",
    "decision_making": "How it makes decisions"
  }},
  "outputs": {{
    "deliverables": ["What it produces/returns"],
    "artifacts": ["Files, reports, changes it creates"],
    "side_effects": ["Actions it takes beyond direct output"]
  }}
}}
```

Be specific and concrete. Extract actual behaviors from the content, not generic
descriptions. If a dimension isn't clearly defined in the content, use
"unspecified" rather than guessing.
""".strip()


# =============================================================================
# AGENT COMPARISON PROMPT
# =============================================================================
# Compares two agents and identifies overlaps, differences, and recommendations

AGENT_COMPARISON_PROMPT = """
Compare these two agents and produce a detailed behavioral diff.

## EXISTING AGENT: {existing_name}
<existing_agent>
{existing_profile}
</existing_agent>

## NEW AGENT: {new_name}
<new_agent>
{new_profile}
</new_agent>

Analyze the behavioral overlap and differences.
Think like a code reviewer examining two implementations.

## Output Format (JSON)

```json
{{
  "summary": {{
    "verdict": "duplicate | variant | complementary | alternative | distinct",
    "one_liner": "One sentence explaining the relationship",
    "overlap_percentage": 0-100
  }},
  "behavioral_diff": {{
    "shared_behaviors": [
      {{
        "behavior": "What both agents do",
        "how_existing": "How existing agent does it",
        "how_new": "How new agent does it",
        "difference": "null if identical, otherwise the nuance"
      }}
    ],
    "only_existing": [
      {{
        "behavior": "What only the existing agent does",
        "importance": "critical | important | minor",
        "gap_impact": "What users lose without this"
      }}
    ],
    "only_new": [
      {{
        "behavior": "What only the new agent does",
        "importance": "critical | important | minor",
        "value_add": "What users gain with this"
      }}
    ]
  }},
  "trigger_overlap": {{
    "competing_triggers": ["Situations where BOTH agents would be invoked"],
    "exclusive_existing": ["Situations only existing handles"],
    "exclusive_new": ["Situations only new handles"]
  }},
  "tool_analysis": {{
    "shared_tools": ["Tools both use"],
    "different_tools_same_purpose": [
      {{"purpose": "...", "existing_uses": "...", "new_uses": "..."}}
    ],
    "unique_tools": {{"existing": [], "new": []}}
  }},
  "recommendation": {{
    "action": "reject | merge | keep_both | replace",
    "reasoning": "Detailed explanation",
    "if_keep_both": "How to disambiguate when to use each",
    "if_merge": "What to combine from each"
  }}
}}
```

Be precise. This diff will help users decide whether to add the new agent.
""".strip()


# =============================================================================
# CONFLICT DETECTION PROMPT
# =============================================================================
# Identifies potential conflicts or confusion between agents

CONFLICT_DETECTION_PROMPT = """
Analyze potential conflicts between these agents.

## Agents to analyze:
{agents_json}

Identify where users might be confused about which agent to use.

## Output Format (JSON)

```json
{{
  "conflicts": [
    {{
      "agents_involved": ["agent1", "agent2"],
      "conflict_type": "trigger_overlap | capability_overlap | domain_overlap",
      "description": "What the conflict is",
      "example_scenario": "A concrete example where confusion would arise",
      "resolution": "How to disambiguate"
    }}
  ],
  "recommendations": [
    "Actionable suggestions for the catalogue maintainer"
  ]
}}
```
""".strip()


# =============================================================================
# DIFF NARRATIVE PROMPT
# =============================================================================
# Generates a human-readable narrative of the diff

DIFF_NARRATIVE_PROMPT = """
Given this behavioral comparison between two agents, write a clear narrative.

## Comparison Data:
{comparison_json}

Write a narrative that:
1. Opens with the verdict (are these duplicates, complementary, etc.)
2. Explains the KEY behavioral overlaps in plain language
3. Highlights the IMPORTANT differences
4. Gives a clear recommendation

Use this format:

**Verdict**: [verdict in bold]

**What They Share**:
[2-3 bullet points of meaningful shared behaviors]

**What's Different**:
[Table or structured comparison of key differences]

**Recommendation**:
[Clear guidance on what to do]

Keep it concise but informative. Users need to make a decision based on this.
""".strip()


# =============================================================================
# QUICK SIMILARITY CHECK PROMPT
# =============================================================================
# Fast check to determine if detailed comparison is needed

QUICK_SIMILARITY_PROMPT = """
Quickly assess if these two agents are potentially similar enough to warrant
detailed comparison.

## Agent 1: {name1}
Purpose: {purpose1}
Capabilities: {capabilities1}
Domains: {domains1}

## Agent 2: {name2}
Purpose: {purpose2}
Capabilities: {capabilities2}
Domains: {domains2}

Respond with JSON:
```json
{{
  "needs_detailed_comparison": true/false,
  "reason": "Brief explanation",
  "estimated_overlap": "high | medium | low | none"
}}
```

Only return true if there's meaningful potential overlap that users should review.
""".strip()
