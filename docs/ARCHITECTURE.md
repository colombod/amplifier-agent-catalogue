# Agent Catalogue Architecture

Technical overview of system design, components, and data flow.

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Frontend                            │
│  (HTML/JS + SSE for real-time updates)                      │
└────────────────────┬────────────────────────────────────────┘
                     │ REST API + SSE
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Backend                            │
│  ├─ API Routes (CRUD, analysis, differentiation)            │
│  ├─ Recipe Routes (multi-stage workflows)                   │
│  └─ SSE Bridge (kernel events → web clients)                │
└────────────────────┬───────────────────┬────────────────────┘
                     │                   │
                     ▼                   ▼
          ┌──────────────────┐  ┌──────────────────┐
          │  SessionManager  │  │  DuckDB Storage  │
          │  (Amplifier)     │  │  (Embeddings +   │
          └────────┬─────────┘  │   Metadata)      │
                   │             └──────────────────┘
                   ▼
          ┌──────────────────────────────────┐
          │    Specialist Agents (9 total)   │
          │  ┌────────────────────────────┐  │
          │  │ extractor, classifier,     │  │
          │  │ evaluator, improver,       │  │
          │  │ differentiator, comparator,│  │
          │  │ narrator, relevance,       │  │
          │  │ discovery                  │  │
          │  └────────────────────────────┘  │
          │                                  │
          │    + 8 Catalogue Tools          │
          │  ┌────────────────────────────┐  │
          │  │ search_similar,            │  │
          │  │ get_agent_content,         │  │
          │  │ store_agent, etc.          │  │
          │  └────────────────────────────┘  │
          └──────────────────────────────────┘
                   │
                   ▼
          ┌──────────────────┐
          │  Azure OpenAI    │
          │  (embeddings)    │
          └──────────────────┘
```

---

## Core Components

### 1. FastAPI Backend

**File**: `src/agent_catalogue/api/`

**Routes**:
- `routes.py` - Core endpoints (agents, analyze, evaluate, improve, refine, search)
- `recipes_routes.py` - Recipe lifecycle endpoints (start, status, approve, cancel, sessions, approvals)

**Responsibilities**:
- HTTP request/response handling
- Input validation (Pydantic models)
- Session orchestration via SessionManager
- Database operations via DuckDB repository

### 2. Amplifier SessionManager

**File**: `src/agent_catalogue/session_manager.py`

**Purpose**: Orchestrates AI agent workflows using Amplifier framework

**Key features**:
- Loads `@recipes` bundle for multi-step workflows
- Creates isolated sessions per operation
- Mounts 8 custom catalogue tools on each session
- Provides `session.spawn` capability for recipe sub-agents
- Manages provider configuration (Anthropic Claude)

**Methods**:
- `startup()` - Initialize with bundle loading
- `run_one_shot(agent_name, prompt)` - Single-turn agent execution
- `_create_session()` - Create temporary session with tools
- `shutdown()` - Clean up all sessions

### 3. DuckDB Storage

**File**: `src/agent_catalogue/storage/repository.py`

**Schema**:
```sql
-- Agents table
agents (
  id UUID PRIMARY KEY,
  name TEXT,
  slug TEXT UNIQUE,
  description TEXT,
  domains TEXT[],
  capabilities TEXT[],
  tools_required TEXT[],
  complexity TEXT,
  embedding FLOAT[3072],  -- Vector for semantic search
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- Versions table (agent evolution tracking)
agent_versions (
  id UUID PRIMARY KEY,
  agent_id UUID REFERENCES agents,
  version_number INTEGER,
  raw_content TEXT,  -- Full AGENTS.md markdown
  metadata JSONB,
  created_at TIMESTAMP
)
```

**Embeddings**: Uses Azure OpenAI `text-embedding-3-large` (3072 dimensions)

**Vector similarity**: Cosine similarity via DuckDB's vector functions

### 4. Specialist Agents

**Location**: `agents/*.md`

**Purpose**: Each agent is a specialist loaded by SessionManager to perform specific tasks

| Agent | Responsibility | Input | Output |
|-------|---------------|-------|--------|
| **extractor** | Parse AGENTS.md, extract metadata | Raw markdown | Structured metadata (JSON) |
| **classifier** | Determine domain, complexity | Metadata | Classifications |
| **evaluator** | Grade quality (A-F) | Agent content | Grade + issues list |
| **improver** | Fix quality issues | Content + issues | Improved markdown |
| **differentiator** | Strategic positioning | Content + competitors | Differentiated markdown |
| **comparator** | Detailed comparison | Two agents | Comparison analysis |
| **narrator** | Human-readable summaries | Agent metadata | Narrative description |
| **relevance** | Context-aware filtering | Query + agents | Relevance scores |
| **discovery** | Help define new agents | User input | Agent definition draft |

**Context files**: `context/*.md` provide domain knowledge to agents

### 5. Catalogue Tools

**Location**: `src/agent_catalogue/tools/`

**Purpose**: Custom Amplifier tools that give agents catalogue access

| Tool | Purpose |
|------|---------|
| **search_similar** | Find similar agents by embedding |
| **get_agent_content** | Fetch full AGENTS.md of specific agent |
| **store_agent** | Save agent to catalogue |
| **update_agent** | Update existing agent |
| **get_agent_versions** | Fetch version history |
| **search_by_capability** | Find agents with specific capability |
| **search_by_domain** | Find agents in domain |
| **get_overlap_report** | Detailed similarity analysis |

**Mounted on**: Every specialist agent session

**Why this matters**: Agents can read the catalogue to understand competitive landscape when differentiating

### 6. SSE Bridge

**File**: `src/agent_catalogue/sse_bridge.py`

**Purpose**: Forward Amplifier kernel events to web clients for real-time feedback

**Event flow**:
```
Amplifier Kernel → SSE Bridge → Web Browser

tool:pre → "→ calling search_similar"
tool:post → "← Found 3 agents"
content_block:end → Agent reasoning displayed
orchestrator:complete → Final result
```

**Streams**:
- `/api/stream/analyze/{workflow_id}`
- `/api/stream/evaluate/{workflow_id}`
- `/api/stream/improve/{workflow_id}`

---

## Data Flow

### Upload & Analysis Flow

```
1. User uploads AGENTS.md (multipart/form-data)
   ↓
2. Backend: POST /api/analyze
   ↓
3. SessionManager.run_one_shot("extractor", content)
   ↓
4. Extractor agent returns JSON metadata
   ↓
5. Embedding generated (Azure OpenAI)
   ↓
6. Vector similarity search (DuckDB)
   ↓
7. Return metadata + similar agents to frontend
   ↓
8. Frontend displays results
```

### Differentiation Flow (Pattern 1)

```
1. User clicks "Refine to Reduce Overlap"
   ↓
2. Frontend: POST /api/refine
   {content, overlapping_agents: [{id, name, capabilities, domains}]}
   ↓
3. Backend fetches FULL content of top 3 overlapping agents
   ↓
4. Builds strategic prompt with differentiation frameworks
   ↓
5. SessionManager.run_one_shot("differentiator", prompt)
   ↓
6. Differentiator agent:
   - Reads competitors using get_agent_content tool
   - Analyzes capability/domain overlap
   - Applies one of 5 strategic frameworks
   - Returns refined markdown
   ↓
7. Backend extracts changes (diff)
   ↓
8. Return RefineResponse {refined_content, changes, metrics}
   ↓
9. Frontend displays refined version with diff
```

### Differentiation Flow (Pattern 2)

```
1. User clicks "Strategic Differentiation"
   ↓
2. Frontend: POST /api/recipe/start
   {recipe_path, context: {content, overlapping_agent_ids}}
   ↓
3. Backend calls recipes tool:
   recipes.execute("differentiate-agent.yaml", context)
   ↓
4. Recipe Stage 1 (strategic-analysis):
   Step 1: analyze-overlap → JSON strategies
   Step 2: format-for-approval → Markdown display
   ↓
5. Recipe PAUSES at approval gate
   ↓
6. Frontend polls: GET /api/recipe/status/{session_id}
   Response: {status: "paused", approval_needed: true, approval_prompt: "..."}
   ↓
7. Frontend shows approval modal with strategies
   ↓
8. User clicks Approve
   ↓
9. Frontend: POST /api/recipe/approve
   {session_id, stage_name: "strategic-analysis", action: "approve"}
   ↓
10. Recipe Stage 2 (strategy-application):
    Step: apply-recommended-strategy → Refined markdown
    ↓
11. Recipe completes
    ↓
12. Frontend polls status → {status: "completed", outputs: {refined_content}}
    ↓
13. Frontend displays final result
```

---

## Technology Stack

### Backend

- **FastAPI** - ASGI web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation
- **Amplifier** - AI agent orchestration framework
- **DuckDB** - Embedded analytics database with vector search

### AI/ML

- **Azure OpenAI** - Text embeddings (text-embedding-3-large, 3072 dims)
- **Anthropic Claude** - Language model (via Amplifier provider)
- **Amplifier Recipes** - Multi-stage workflow orchestration

### Frontend

- **Vanilla HTML/CSS/JS** - No framework dependencies
- **Server-Sent Events** - Real-time progress updates
- **Fetch API** - REST communication

### Storage

- **DuckDB** - Agents, versions, embeddings
- **Filesystem** - Recipe session state (`.amplifier/projects/`)

---

## Key Design Decisions

### Why DuckDB?

- **Embedded** - No separate database server
- **Vector search** - Native cosine similarity for embeddings
- **OLAP optimized** - Fast analytics queries
- **Portable** - Single file database

### Why Amplifier?

- **Modular** - Swap providers, tools, orchestrators
- **Event-driven** - Complete audit trail
- **Recipes** - Built-in approval gates and workflow management
- **Session isolation** - Each operation is independent

### Why Two Differentiation Patterns?

Different users have different needs:
- **Simple Refine** - "Just make it different" (trust the AI)
- **Strategic** - "Show me options" (strategic decisions)

Both are valuable - we support both.

### Why Custom Tools?

Agents need catalogue access to:
- Read competitor agents when differentiating
- Search for positioning gaps
- Validate improvement suggestions
- Provide context-aware recommendations

Standard tools (bash, web_search) can't access internal catalogue state.

---

## Performance Considerations

### Embedding Generation

- **Latency**: ~200-500ms per agent
- **Cost**: ~$0.0001 per 1000 tokens (negligible)
- **Caching**: Embeddings cached per agent version

### LLM Calls

- **Extractor**: ~5-10 seconds (metadata extraction)
- **Evaluator**: ~8-12 seconds (quality grading)
- **Improver**: ~15-20 seconds (content rewrite)
- **Differentiator**: ~15-25 seconds (strategic positioning)

### Recipe Execution (Pattern 2)

- **Stage 1** (strategic-analysis): ~30-45 seconds (2 LLM calls)
- **User approval**: Variable (human wait time)
- **Stage 2** (strategy-application): ~20-30 seconds (1 LLM call)
- **Total**: ~1-3 minutes (including user interaction)

### Database Queries

- **Vector similarity**: <100ms for 1000 agents
- **Metadata queries**: <50ms
- **Scales well**: DuckDB handles millions of vectors

---

## Event System

### Amplifier Kernel Events

Every agent operation emits structured events:

```json
{"event": "tool:pre", "tool_name": "search_similar", "input": {...}}
{"event": "tool:post", "tool_name": "search_similar", "result": {...}}
{"event": "content_block:end", "content": "Agent reasoning..."}
{"event": "orchestrator:complete", "response": "Final result"}
```

### SSE Bridge Translation

The SSE bridge converts kernel events to user-friendly messages:

| Kernel Event | SSE Message |
|--------------|-------------|
| `tool:pre` | "→ Calling search_similar" |
| `tool:post` (success) | "← Found 3 similar agents" |
| `tool:post` (error) | "✗ Search failed: timeout" |
| `content_block:end` | "▸ Agent reasoning: ..." |
| `orchestrator:complete` | Final result displayed |

**File**: `src/agent_catalogue/sse_bridge.py`

---

## Security Considerations

### Current State

- **No authentication** - Open access (development only)
- **No rate limiting** - Unlimited requests
- **No input sanitization** - Trusts all markdown input
- **API keys required** - Azure OpenAI + Anthropic (stored in .env)

### Production Requirements

Before deploying publicly:
- [ ] Add authentication (API keys or OAuth2)
- [ ] Implement rate limiting (100 req/min per user)
- [ ] Sanitize markdown input (prevent XSS)
- [ ] Add CORS configuration
- [ ] Use secrets manager for API keys (not .env)
- [ ] Add request logging and monitoring
- [ ] Implement user quotas (LLM cost control)

---

## Deployment Architecture

### Development

```bash
agent-catalogue serve --host 127.0.0.1 --port 8000
```

**Process**:
- Uvicorn ASGI server
- Hot reload enabled
- Debug logging to `/tmp/agent-catalogue-debug.log`

### Production (Recommended)

```bash
# Behind reverse proxy (Nginx/Caddy)
agent-catalogue serve --host 127.0.0.1 --port 8000
```

**Reverse proxy config** (Nginx):
```nginx
server {
    listen 80;
    server_name catalogue.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /api/stream/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

**Why reverse proxy**:
- SSL/TLS termination
- Rate limiting
- Request logging
- Static file serving
- Load balancing (if needed)

---

## File Structure

```
amplifier-app-agent-catalogue/
├── agents/                    # Amplifier agent definitions
│   ├── extractor.md
│   ├── classifier.md
│   ├── evaluator.md
│   ├── improver.md
│   ├── differentiator.md
│   ├── comparator.md
│   ├── narrator.md
│   ├── relevance.md
│   └── discovery.md
│
├── context/                   # Knowledge files for agents
│   ├── agent-anatomy.md       # What makes good AGENTS.md
│   ├── quality-criteria.md    # Grading rubric
│   ├── comparison-methodology.md
│   ├── behavior-patterns.md
│   └── domain-taxonomy.md
│
├── recipes/                   # Multi-step workflows
│   └── differentiate-agent.yaml
│
├── src/agent_catalogue/
│   ├── api/
│   │   ├── routes.py          # Core REST endpoints
│   │   └── recipes_routes.py  # Recipe lifecycle endpoints
│   ├── models/
│   │   ├── agent.py           # Agent, Version models
│   │   └── requests.py        # API request/response models
│   ├── services/
│   │   ├── extraction.py      # Metadata extraction
│   │   ├── embedding.py       # Azure OpenAI embeddings
│   │   └── similarity.py      # Vector search
│   ├── storage/
│   │   └── repository.py      # DuckDB operations
│   ├── tools/                 # Amplifier catalogue tools
│   │   ├── search.py          # search_similar, search_by_*
│   │   ├── storage.py         # get_*, store_*, update_*
│   │   └── analysis.py        # get_overlap_report
│   ├── web/
│   │   ├── templates/         # HTML templates
│   │   └── static/            # CSS, JS, images
│   ├── session_manager.py     # Amplifier orchestration
│   └── sse_bridge.py          # Real-time events
│
├── tests/                     # Test suite
├── docs/                      # Documentation
└── data/                      # DuckDB database file
```

---

## Extension Points

### Adding New Specialist Agents

1. Create `agents/new-agent.md` with agent definition
2. SessionManager will auto-discover via `paths.py:get_agents_dir()`
3. Call via: `session_mgr.run_one_shot("new-agent", prompt)`

**No code changes needed** - agents are configuration, not code.

### Adding New Catalogue Tools

1. Create tool class in `src/agent_catalogue/tools/`
2. Implement Amplifier Tool contract:
   ```python
   class NewTool:
       @property
       def name(self) -> str: ...
       def get_schema(self) -> dict: ...
       @property
       def input_schema(self) -> dict: ...
       async def execute(self, input: dict) -> ToolResult: ...
   ```
3. Register in `session_manager.py:_create_session()`

### Adding New Recipes

1. Create `recipes/new-workflow.yaml`
2. Define stages, steps, approval gates
3. Reference in API endpoint: `recipe_path="recipes/new-workflow.yaml"`

**See**: `@recipes:docs/RECIPE_SCHEMA.md` for recipe syntax

---

## Debugging

### Server Logs

```bash
# Comprehensive debug log
tail -f /tmp/agent-catalogue-debug.log

# What's logged:
# - Tool executions (search_similar, get_agent_content)
# - Agent calls (differentiator, evaluator)
# - Database queries (embedding generation, similarity)
# - API requests (refine, analyze, improve)
# - Errors with stack traces
```

### Recipe Session State

```bash
# Recipe sessions stored in:
~/.amplifier/projects/agent-catalogue/recipe-sessions/

# Each session has:
session_id/
├── events.jsonl     # Complete event log
├── state.json       # Current state + outputs
└── metadata.json    # Recipe definition
```

### Frontend Debugging

Open browser console - all SSE events are logged:
```javascript
console.log("SSE Event:", event_type, data);
```

---

## Testing Strategy

### Unit Tests

```bash
# Fast, no LLM calls
pytest tests/unit/
```

### Integration Tests

```bash
# Requires server + LLM, slower
pytest tests/integration/
```

### Endpoint Tests

```bash
# Quick endpoint verification (no LLM)
.venv/bin/python tests/test_recipe_endpoints_quick.py
```

### Live Server Tests

```bash
# Requires running server
agent-catalogue serve &
.venv/bin/python tests/test_refine_live.py
```

**See**: `tests/README.md` for complete testing guide

---

## Dependencies

### Python Packages

**Core**:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `amplifier-core` - Agent framework kernel
- `amplifier-foundation` - Bundle primitives
- `amplifier-bundle-recipes` - Workflow orchestration

**Data**:
- `duckdb` - Embedded database
- `pydantic` - Data validation
- `azure-identity` - Azure auth
- `openai` - Embeddings client

**Dev**:
- `pytest` - Testing
- `ruff` - Linting
- `pyright` - Type checking
- `playwright` - Browser automation

### External Services

**Required**:
- Azure OpenAI (embeddings)
- Anthropic API (LLM)

**Optional**:
- Azure RBAC (for key-less auth)

---

## Future Architecture

### Planned Enhancements

1. **Multi-tenancy**: Separate catalogues per user/org
2. **Collaboration**: Share agents, comment, rate
3. **Analytics**: Track which agents are most used
4. **API versioning**: /v1/ prefix for stability
5. **Batch operations**: Upload multiple agents
6. **Export formats**: JSON, YAML, bundle packages

### Scaling Considerations

**Current** (single instance):
- Handles ~100 concurrent users
- ~10K agents in catalogue
- Embedding generation is bottleneck

**Scaling path**:
1. **Horizontal scaling** - Multiple FastAPI instances behind load balancer
2. **Separate embedding service** - Dedicated worker pool
3. **PostgreSQL** - Replace DuckDB for multi-instance read/write
4. **Redis** - Cache embeddings and similarity results
5. **CDN** - Static assets and cached responses

**But**: Start simple. Current architecture is sufficient for thousands of users.

---

## Related Documentation

- **User Guide**: `docs/USER_GUIDE.md` - How to use the web interface
- **API Reference**: `docs/API.md` - Complete endpoint documentation
- **Differentiation Patterns**: `docs/DIFFERENTIATION_PATTERNS.md` - Pattern 1 vs 2
- **Event Flow**: `docs/EVENT_FLOW.md` - SSE architecture details

---

**Questions about architecture?** See source code or create an issue.
