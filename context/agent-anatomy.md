# Skill: Agent Anatomy

Understanding the structure and components of AGENTS.md files.

## What is an AGENTS.md File?

An AGENTS.md file defines the behavior, capabilities, and constraints of an AI agent. It's a markdown document that instructs an AI system how to behave in a specific context.

## Core Components

### 1. Identity Section
The agent's name, role, and primary purpose.

**Look for:**
- Title/heading (usually H1)
- Role description ("You are a...", "This agent is...")
- Mission statement

**Extract:**
- `name`: The agent's identifier
- `primary_role`: One sentence describing what this agent IS
- `mission`: What it's trying to accomplish

### 2. Trigger Conditions
When this agent should be invoked.

**Look for:**
- "Use this agent when..."
- "Invoke for..."
- "Delegate to this agent if..."
- Keyword lists
- Scenario descriptions

**Extract:**
- `when_to_use`: List of specific situations
- `input_types`: Types of requests it handles
- `keywords`: Words/phrases that suggest this agent

### 3. Capabilities
What the agent can do.

**Look for:**
- "Can do:", "Capabilities:", "Features:"
- Action verbs (analyze, generate, review, fix)
- Tool references (bash, grep, LSP, web_search)
- Methodology descriptions

**Extract:**
- `can_do`: Specific actions it performs
- `approach`: HOW it approaches problems
- `tools_used`: Tools/commands it employs

### 4. Constraints
What the agent cannot or should not do.

**Look for:**
- "Cannot:", "Limitations:", "Boundaries:"
- "Defers to...", "Hands off to..."
- Scope limitations
- Explicit prohibitions

**Extract:**
- `cannot_do`: Explicit limitations
- `defers_to`: Other agents it delegates to
- `boundaries`: Scope it respects

### 5. Interaction Style
How the agent communicates and makes decisions.

**Look for:**
- Communication tone descriptions
- Autonomy indicators ("ask before...", "proceed without...")
- Decision-making patterns

**Extract:**
- `communication`: How it talks to users
- `autonomy_level`: autonomous | guided | collaborative
- `decision_making`: How it makes decisions

### 6. Outputs
What the agent produces.

**Look for:**
- "Produces:", "Returns:", "Delivers:"
- File types mentioned
- Report formats
- Side effects described

**Extract:**
- `deliverables`: What it produces
- `artifacts`: Files, reports it creates
- `side_effects`: Actions beyond direct output

## Quality Indicators

### Well-Defined Agent
- Clear, specific trigger conditions
- Explicit capability boundaries
- Documented tool usage
- Defined handoff patterns

### Poorly-Defined Agent
- Vague trigger conditions ("use when appropriate")
- Unclear boundaries
- No tool documentation
- Missing delegation patterns

## Common Patterns

### Specialist Pattern
- Narrow focus, deep expertise
- Specific trigger keywords
- Limited tool set
- Clear handoffs

### Orchestrator Pattern
- Broad scope
- Delegates to specialists
- Light on direct capabilities
- Heavy on routing logic

### Hybrid Pattern
- Some direct capabilities
- Some delegation
- Context-dependent behavior
