# Skill: Domain Taxonomy

Classification system for categorizing AI agents by domain, complexity, and autonomy.

## Domain Categories

### Development Domains

**Code Quality**
- Linting, formatting, style
- Code review, best practices
- Technical debt analysis
- Keywords: lint, format, style, review, quality

**Debugging**
- Error investigation
- Root cause analysis
- Fix generation
- Keywords: debug, error, fix, bug, investigate

**Testing**
- Test generation
- Coverage analysis
- Test execution
- Keywords: test, coverage, assert, mock, spec

**Architecture**
- System design
- Pattern application
- Refactoring decisions
- Keywords: architect, design, pattern, refactor, structure

**Documentation**
- Code documentation
- API docs
- README generation
- Keywords: document, readme, api-doc, comment

**Security**
- Vulnerability scanning
- Security review
- Threat modeling
- Keywords: security, vulnerability, CVE, OWASP, audit

**Performance**
- Profiling
- Optimization
- Bottleneck analysis
- Keywords: performance, optimize, profile, benchmark, latency

### Operations Domains

**DevOps**
- CI/CD pipelines
- Infrastructure as code
- Deployment automation
- Keywords: deploy, pipeline, CI, CD, infrastructure

**Git Operations**
- Version control
- Branching, merging
- PR management
- Keywords: git, commit, branch, merge, PR, rebase

**Cloud**
- Cloud resource management
- Service configuration
- Cost optimization
- Keywords: AWS, Azure, GCP, cloud, serverless

### Knowledge Domains

**Research**
- Information gathering
- Synthesis
- Citation
- Keywords: research, search, find, investigate, explore

**Exploration**
- Codebase navigation
- Understanding existing systems
- Mapping dependencies
- Keywords: explore, survey, understand, map, navigate

**Learning**
- Teaching concepts
- Explaining code
- Tutorial generation
- Keywords: explain, teach, learn, tutorial, how-to

### Workflow Domains

**Planning**
- Task breakdown
- Roadmap creation
- Estimation
- Keywords: plan, roadmap, estimate, breakdown, schedule

**Orchestration**
- Multi-agent coordination
- Workflow management
- Task routing
- Keywords: orchestrate, coordinate, delegate, route

**Integration**
- API integration
- Service connection
- Data flow
- Keywords: integrate, connect, API, webhook, sync

## Complexity Levels

### Simple
- Single task focus
- Clear input → output
- Minimal decision branching
- Few tools (0-2)
- Example: "Format this code"

### Moderate
- Multi-step workflows
- Some conditional logic
- Medium tool usage (3-5)
- Domain expertise required
- Example: "Review this PR for security issues"

### Complex
- Multi-domain awareness
- Significant decision trees
- Heavy tool usage (5+)
- Deep expertise required
- Example: "Refactor this module while maintaining backward compatibility"

### Expert
- Cross-cutting concerns
- Novel problem solving
- Orchestration of other agents
- Judgment-heavy decisions
- Example: "Design the architecture for this new feature"

## Autonomy Levels

### Level 1: Assisted
- Requires confirmation for all actions
- Presents options, user decides
- No side effects without approval
- Trust: Low

### Level 2: Supervised
- Executes safe operations automatically
- Confirms risky operations
- Reports after completion
- Trust: Medium

### Level 3: Autonomous
- Makes most decisions independently
- Acts without confirmation
- Reports summary of actions
- Trust: High

### Level 4: Fully Autonomous
- Complete independence
- May spawn sub-agents
- Handles edge cases alone
- Trust: Very High

## Classification Algorithm

### Step 1: Identify Primary Domain
1. Extract keywords from agent content
2. Match against domain keyword lists
3. Select domain with highest match count
4. If tie, use capability analysis

### Step 2: Identify Secondary Domains
1. Find additional domain matches
2. Include if match count > threshold
3. Order by relevance

### Step 3: Assess Complexity
Score each factor (0-3):
- Number of capabilities
- Number of tools
- Decision branching
- Domain depth required

```
complexity = sum(scores) / max_possible
if complexity < 0.25: "simple"
elif complexity < 0.5: "moderate"
elif complexity < 0.75: "complex"
else: "expert"
```

### Step 4: Assess Autonomy
Look for indicators:
- "ask before" → reduces autonomy
- "automatically" → increases autonomy
- "confirm" → reduces autonomy
- "proceed" → increases autonomy

Count positive vs negative indicators.

## Tag Generation

Generate searchable tags from:

1. **Domain tags**: Primary and secondary domains
2. **Capability tags**: Key capabilities as tags
3. **Tool tags**: Tools used
4. **Pattern tags**: Behavioral patterns identified
5. **Quality tags**: Complexity, autonomy levels

### Tag Format
- Lowercase, hyphenated
- Prefixed by category: `domain:debugging`, `tool:grep`, `pattern:specialist`

## Search Optimization

For effective agent discovery:

1. **Primary match**: Domain + capability alignment
2. **Secondary match**: Tool overlap
3. **Tertiary match**: Pattern similarity

Weight search results:
```
score = (
    0.4 × domain_match +
    0.3 × capability_match +
    0.2 × tool_match +
    0.1 × pattern_match
)
```
