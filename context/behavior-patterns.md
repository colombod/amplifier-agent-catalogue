# Skill: Behavior Patterns

Common behavioral patterns found in AI agents and how to identify them.

## Behavioral Dimensions

### 1. Autonomy Spectrum

**Autonomous**
- Acts without confirmation
- Makes decisions independently
- Reports results after completion
- Indicators: "proceed without asking", "automatically", "by default"

**Guided**
- Asks for confirmation on key decisions
- Presents options before acting
- Checks in at milestones
- Indicators: "confirm before", "ask the user", "present options"

**Collaborative**
- Works alongside user continuously
- Iterative back-and-forth
- Shared decision-making
- Indicators: "together", "iteratively", "with user input"

### 2. Scope Patterns

**Narrow Specialist**
- Single domain expertise
- Deep knowledge in one area
- Clear boundaries
- Examples: "SQL optimizer", "CSS debugger", "Git expert"

**Broad Generalist**
- Multiple domain awareness
- Shallow-to-medium knowledge
- Flexible boundaries
- Examples: "General assistant", "Project helper"

**Domain Expert**
- Single domain, comprehensive coverage
- Both broad and deep
- Authoritative in domain
- Examples: "Python expert", "Security specialist"

### 3. Interaction Patterns

**Reactive**
- Responds to explicit requests
- Waits for instructions
- Minimal initiative
- Indicators: "when asked", "upon request"

**Proactive**
- Anticipates needs
- Suggests improvements
- Takes initiative
- Indicators: "automatically suggest", "proactively check"

**Advisory**
- Provides recommendations
- Explains tradeoffs
- Defers final decision
- Indicators: "recommend", "suggest", "advise"

### 4. Tool Usage Patterns

**Tool-Heavy**
- Relies extensively on tools
- Multiple tool chains
- Tool-first approach
- Indicators: Many tool references, complex workflows

**Tool-Light**
- Primarily reasoning-based
- Minimal tool usage
- Knowledge-first approach
- Indicators: Few tool references, emphasis on analysis

**Tool-Specific**
- Specialized tool expertise
- Deep tool knowledge
- Tool mastery
- Indicators: Detailed tool instructions, edge cases covered

### 5. Output Patterns

**Analytical**
- Produces analysis, insights
- Explanatory outputs
- Understanding-focused
- Outputs: Reports, explanations, assessments

**Generative**
- Creates new content
- Productive outputs
- Creation-focused
- Outputs: Code, documents, designs

**Transformative**
- Modifies existing content
- Improvement-focused
- Refinement outputs
- Outputs: Refactored code, edited documents

**Orchestrative**
- Coordinates other agents/processes
- Meta-level outputs
- Coordination-focused
- Outputs: Plans, delegations, workflows

## Behavioral Signatures

### The Debugger
- Trigger: Errors, failures, unexpected behavior
- Approach: Hypothesis-driven, systematic
- Tools: Logs, debuggers, profilers
- Output: Root cause, fix recommendation

### The Reviewer
- Trigger: Code/content for review
- Approach: Criteria-based evaluation
- Tools: Linters, analyzers, checklists
- Output: Feedback, suggestions, approval/rejection

### The Builder
- Trigger: Implementation requests
- Approach: Specification-driven, modular
- Tools: Editors, compilers, test runners
- Output: Working code/artifacts

### The Explorer
- Trigger: Unknown codebase, investigation
- Approach: Survey, map, summarize
- Tools: Search, grep, file readers
- Output: Understanding, documentation

### The Architect
- Trigger: Design decisions, system planning
- Approach: Principles-first, tradeoff analysis
- Tools: Diagramming, modeling
- Output: Designs, specifications, decisions

### The Guardian
- Trigger: Security, safety, compliance
- Approach: Threat modeling, validation
- Tools: Scanners, validators, auditors
- Output: Vulnerabilities, recommendations

## Pattern Combinations

Agents often combine multiple patterns:

**Proactive Specialist** = Proactive + Narrow
- Deep expertise with initiative
- Suggests improvements in domain

**Collaborative Builder** = Collaborative + Generative
- Creates with user involvement
- Iterative development

**Autonomous Guardian** = Autonomous + Guardian
- Continuous security monitoring
- Acts without prompting

## Identifying Patterns

When analyzing an agent, identify:

1. **Primary behavior**: What does it do most?
2. **Trigger pattern**: What invokes it?
3. **Tool pattern**: How does it use tools?
4. **Output pattern**: What does it produce?
5. **Interaction pattern**: How does it engage?

This creates a behavioral fingerprint for comparison.
