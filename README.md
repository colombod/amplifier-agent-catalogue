# Agent Catalogue

A web application for cataloguing, versioning, and discovering AI agent definitions (AGENTS.md files), powered by [Amplifier](https://github.com/microsoft/amplifier).

**Live Repository**: https://github.com/colombod/amplifier-agent-catalogue

---

## What It Does

Agent Catalogue helps you manage and discover AI agent definitions:

- **Upload & Analyze** - Extract metadata from AGENTS.md files
- **Quality Evaluation** - Grade agent definitions (A-F scale)
- **Similarity Detection** - Find overlapping agents in the catalogue
- **Smart Differentiation** - AI-powered positioning strategies to reduce overlap
- **Version Management** - Track agent evolution over time
- **Semantic Search** - Find agents by capabilities, domains, or purpose

---

## Architecture

### Tech Stack

- **Backend**: FastAPI + Amplifier (AI agent framework)
- **Storage**: DuckDB (embedded database with vector search)
- **Embeddings**: Azure OpenAI (text-embedding-3-large)
- **LLM**: Anthropic Claude (via Amplifier providers)
- **Frontend**: HTML/JavaScript + SSE for real-time updates

### Key Components

**Amplifier Integration**:
- SessionManager orchestrates AI agent workflows
- 5 specialist agents (extractor, classifier, evaluator, improver, differentiator)
- 8 custom catalogue tools (search_similar, get_agent_content, etc.)
- Recipes bundle for multi-step workflows with approval gates

**API Endpoints**:
- REST API for CRUD operations
- Streaming endpoints (SSE) for real-time agent execution feedback
- Recipe endpoints for multi-stage workflows

---

## Features

### 1. Upload & Analysis

Upload an AGENTS.md file and get:
- Extracted metadata (name, capabilities, domains, tools, complexity)
- Automatic classification
- Similar agents detection
- Quality evaluation with actionable feedback

### 2. Differentiation Patterns ✅ Both Production-Ready

**Pattern 1: Simple Refine** ✅ (One-click differentiation)
- Endpoint: `POST /api/refine`
- Flow: Upload → Detect overlap → Click "Refine" → Get differentiated version
- Speed: ~15 seconds
- Best for: Quick improvements

**Pattern 2: Strategic Differentiation** ✅ (Multi-stage with approval gates)
- Endpoints: 6 recipe lifecycle endpoints
- Flow: Start → Review strategies → Approve → Apply
- Speed: ~30-90 seconds
- Best for: Strategic positioning decisions
- Status: Fully implemented (backend + frontend, Feb 2026)

### 3. Quality Improvement

AI-powered quality improvement:
- Identifies clarity, specificity, structure issues
- Suggests concrete fixes
- Preserves your agent's core purpose
- Validates improvements automatically

---

## API Endpoints

### Core Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/agents` | GET | List all agents |
| `/api/agents/{slug}` | GET | Get specific agent |
| `/api/analyze` | POST | Extract metadata & find similar |
| `/api/evaluate` | POST | Quality evaluation |
| `/api/improve` | POST | AI-powered improvement |
| `/api/refine` | POST | Differentiation (Pattern 1) |
| `/api/search` | GET | Semantic search |

### Recipe Endpoints (Pattern 2) ✅

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/recipe/start` | POST | Start recipe execution | ✅ Implemented |
| `/api/recipe/status/{session_id}` | GET | Poll recipe status | ✅ Implemented |
| `/api/recipe/sessions` | GET | List all recipe sessions | ✅ Implemented |
| `/api/recipe/approvals` | GET | List pending approvals | ✅ Implemented |
| `/api/recipe/approve` | POST | Approve/deny stage | ✅ Implemented |
| `/api/recipe/cancel/{session_id}` | POST | Cancel execution | ✅ Implemented |

### Streaming Endpoints (SSE)

| Endpoint | Purpose |
|----------|---------|
| `/api/stream/analyze/{workflow_id}` | Real-time analysis progress |
| `/api/stream/evaluate/{workflow_id}` | Real-time evaluation progress |
| `/api/stream/improve/{workflow_id}` | Real-time improvement progress |

---

## Setup

### Prerequisites

- Python 3.11+
- Azure OpenAI access (for embeddings)
- Anthropic API key (for LLM)

### Installation

```bash
# Clone repository
git clone https://github.com/colombod/amplifier-agent-catalogue.git
cd amplifier-agent-catalogue

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"
```

### Configuration

Create `.env` file (copy from `.env.example`):

```bash
# Azure OpenAI (for embeddings)
AS_AZURE_OPENAI_ENDPOINT=https://your-instance.cognitiveservices.azure.com/
AS_AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AS_AZURE_OPENAI_EMBEDDING_MODEL=text-embedding-3-large
AS_AZURE_OPENAI_EMBEDDING_DIMENSIONS=3072
AS_AZURE_OPENAI_USE_RBAC=true  # Or set API key

# Anthropic (for LLM via Amplifier)
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

### Start Server

```bash
# Development
agent-catalogue serve

# Production
agent-catalogue serve --host 0.0.0.0 --port 8000
```

### Web Interface

Open http://localhost:8000

**Workflow**:
1. Upload AGENTS.md file
2. Review extracted metadata and similar agents
3. Get quality evaluation
4. Improve if needed
5. Differentiate if overlaps detected
6. Store in catalogue

### CLI Commands

```bash
# Start web server
agent-catalogue serve [--host HOST] [--port PORT] [--reload]

# Check version
agent-catalogue --version
```

---

## Development

### Project Structure

```
amplifier-app-agent-catalogue/
├── src/agent_catalogue/
│   ├── api/              # FastAPI routes
│   │   ├── routes.py       # Core endpoints
│   │   └── recipes_routes.py  # Recipe endpoints
│   ├── models/           # Pydantic models
│   ├── services/         # Business logic
│   ├── storage/          # DuckDB repository
│   ├── tools/            # Amplifier catalogue tools
│   ├── web/              # Templates & static files
│   ├── session_manager.py  # Amplifier session orchestration
│   └── sse_bridge.py     # Real-time event streaming
├── agents/               # Amplifier agent definitions
├── context/              # Knowledge files for agents
├── recipes/              # Multi-step workflows
├── tests/                # Test suite
└── docs/                 # Documentation
```

### Running Tests

```bash
# Quick endpoint verification (fast, no LLM)
.venv/bin/python tests/test_recipe_endpoints_quick.py

# Filesystem helpers test
.venv/bin/python tests/test_recipe_helpers.py

# Full test suite (requires LLM, slower)
pytest tests/

# Code quality
ruff check src/ tests/
pyright src/ tests/
```

### Key Concepts

**Amplifier Integration**:
- Uses Amplifier's modular architecture (providers, tools, orchestrators, hooks)
- Loads `@recipes` bundle for multi-step workflows
- SessionManager creates isolated sessions per operation
- SSE bridge streams Amplifier kernel events to web UI

**Agent Specialists**:
- **extractor** - Extract metadata from AGENTS.md
- **classifier** - Classify domain and complexity
- **evaluator** - Quality grading (1-10 scale)
- **improver** - Fix quality issues
- **differentiator** - Strategic positioning

**Tools**:
- 8 custom catalogue tools for agent operations
- Mounted on each specialist session
- Enable agents to search, read, analyze catalogue

---

## Documentation

| Doc | Purpose |
|-----|---------|
| `README.md` | This file - project overview |
| `docs/DIFFERENTIATION_SYSTEM.md` | Architecture & design |
| `docs/DIFFERENTIATION_PATTERNS.md` | Pattern 1 vs Pattern 2 comparison |
| `docs/RECIPE_INTEGRATION.md` | Recipe endpoint implementation |
| `docs/EVENT_FLOW.md` | SSE event architecture |
| `docs/INTEGRATION_SUMMARY.md` | Executive summary |
| `PATTERN2_COMPLETE.md` | Pattern 2 implementation notes |
| `TEST_RESULTS.md` | Test verification results |

---

## Contributing

This is a personal project by @colombod. Issues and PRs welcome!

### Development Workflow

1. Create feature branch
2. Make changes with tests
3. Run quality checks
4. Commit with descriptive messages
5. Push and create PR

### Commit Message Format

```
type: short description

Longer explanation if needed.

🤖 Generated with Amplifier
Co-Authored-By: Amplifier <240397093+microsoft-amplifier@users.noreply.github.com>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

---

## License

[Add license information]

---

## Credits

Built with:
- [Amplifier](https://github.com/microsoft/amplifier) - AI agent framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [DuckDB](https://duckdb.org/) - Embedded database
- [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) - Embeddings
- [Anthropic Claude](https://www.anthropic.com/) - Language model
