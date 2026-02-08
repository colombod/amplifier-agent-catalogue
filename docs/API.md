# Agent Catalogue API Reference

Complete reference for all REST endpoints.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: Configure via deployment

## Authentication

Currently none. Future: API key or OAuth2.

---

## Agent Management

### List All Agents

```http
GET /api/agents
```

**Query Parameters**:
- `limit` (int, optional): Max results (default: 100)
- `offset` (int, optional): Pagination offset (default: 0)

**Response**:
```json
{
  "agents": [
    {
      "id": "uuid",
      "name": "Agent Name",
      "slug": "agent-name",
      "description": "Brief description",
      "domains": ["domain1", "domain2"],
      "capabilities": ["cap1", "cap2"],
      "created_at": "2026-02-01T12:00:00Z"
    }
  ],
  "total": 42
}
```

### Get Specific Agent

```http
GET /api/agents/{slug}
```

**Response**:
```json
{
  "agent": {...},
  "latest_version": {
    "version_number": 3,
    "raw_content": "# Agent markdown...",
    "created_at": "2026-02-08T01:00:00Z"
  },
  "versions": [...]
}
```

---

## Analysis & Improvement

### Analyze Agent

```http
POST /api/analyze
```

**Request** (multipart/form-data):
- `file`: AGENTS.md file

**Response**:
```json
{
  "metadata": {
    "name": "Extracted Name",
    "capabilities": [...],
    "domains": [...],
    "tools": [...],
    "complexity": "medium"
  },
  "similar_agents": [
    {
      "id": "uuid",
      "name": "Similar Agent",
      "similarity": 0.85,
      "overlap_summary": "Shares 5 capabilities..."
    }
  ]
}
```

### Evaluate Quality

```http
POST /api/evaluate
```

**Request**:
```json
{
  "content": "# Agent markdown..."
}
```

**Response**:
```json
{
  "grade": "B+",
  "score": 8.5,
  "issues": [
    {
      "category": "clarity",
      "severity": "medium",
      "description": "Description could be more specific",
      "suggestion": "Add concrete examples of when to use"
    }
  ]
}
```

### Improve Agent

```http
POST /api/improve
```

**Request**:
```json
{
  "content": "# Agent markdown...",
  "issues": [...]  // From /api/evaluate
}
```

**Response**:
```json
{
  "improved_content": "# Improved markdown...",
  "changes": [
    {
      "section": "Description",
      "change": "Added specific use cases",
      "reason": "Improves clarity"
    }
  ]
}
```

---

## Differentiation

### Pattern 1: Simple Refine ✅

```http
POST /api/refine
```

**Request**:
```json
{
  "content": "# Agent markdown...",
  "overlapping_agents": [
    {
      "id": "uuid",
      "name": "Overlapping Agent",
      "capabilities": [...],
      "domains": [...]
    }
  ]
}
```

**Response** (~15s):
```json
{
  "refined_content": "# Refined markdown...",
  "changes": [
    {
      "section": "Capabilities",
      "before": "General Python helper",
      "after": "FastAPI testing specialist",
      "strategy": "narrow_scope"
    }
  ],
  "token_metrics": {
    "before": 800,
    "after": 1200,
    "delta": 400
  }
}
```

**Performance**: ~15 seconds average

### Pattern 2: Strategic Differentiation ✅

Multi-stage workflow with approval gates.

#### Start Recipe

```http
POST /api/recipe/start
```

**Request**:
```json
{
  "recipe_path": "recipes/differentiate-agent.yaml",
  "context": {
    "content": "# Agent markdown...",
    "overlapping_agent_ids": ["uuid1", "uuid2"],
    "attempt_number": 1
  }
}
```

**Response**:
```json
{
  "session_id": "recipe_20260208_...",
  "status": "running"
}
```

#### Poll Status

```http
GET /api/recipe/status/{session_id}
```

**Response** (when running):
```json
{
  "status": "running",
  "stage_name": "strategic-analysis",
  "outputs": {}
}
```

**Response** (when approval needed):
```json
{
  "status": "paused",
  "stage_name": "strategic-analysis",
  "approval_needed": true,
  "approval_prompt": "Review strategies:\n\nStrategy 1: Narrow Scope...\nStrategy 2: Different Approach...\n\nRecommended: Strategy 1\n\nApprove to apply recommendation, Deny to cancel.",
  "outputs": {
    "analysis": {
      "strategies": [...],
      "recommended_index": 0
    }
  }
}
```

**Response** (when complete):
```json
{
  "status": "completed",
  "outputs": {
    "refined_content": "# Refined markdown..."
  }
}
```

#### Approve/Deny Stage

```http
POST /api/recipe/approve
```

**Request**:
```json
{
  "session_id": "recipe_20260208_...",
  "stage_name": "strategic-analysis",
  "action": "approve"  // or "deny"
}
```

**Response**:
```json
{
  "status": "resumed"
}
```

**Then**: Continue polling `/api/recipe/status/{session_id}` until `status: "completed"`

#### List Sessions

```http
GET /api/recipe/sessions
```

**Response**:
```json
{
  "sessions": [
    {
      "session_id": "recipe_20260208_...",
      "status": "completed",
      "created_at": "2026-02-08T01:00:00Z"
    }
  ]
}
```

#### List Pending Approvals

```http
GET /api/recipe/approvals
```

**Response**:
```json
{
  "approvals": [
    {
      "session_id": "recipe_20260208_...",
      "stage_name": "strategic-analysis",
      "approval_prompt": "Review strategies..."
    }
  ]
}
```

#### Cancel Recipe

```http
POST /api/recipe/cancel/{session_id}
```

**Request Body**:
```json
{
  "immediate": false  // true for immediate cancel, false for graceful
}
```

**Response**:
```json
{
  "status": "cancelled"
}
```

---

## Search

### Semantic Search

```http
GET /api/search?q=query&limit=10
```

**Query Parameters**:
- `q` (string, required): Search query
- `limit` (int, optional): Max results (default: 10)

**Response**:
```json
{
  "results": [
    {
      "id": "uuid",
      "name": "Agent Name",
      "similarity": 0.92,
      "match_summary": "Matches query on capabilities: testing, Python"
    }
  ]
}
```

---

## Streaming Endpoints (SSE)

Real-time progress updates via Server-Sent Events.

### Stream Analysis

```http
GET /api/stream/analyze/{workflow_id}
```

**Events**:
```
event: tool_call
data: {"tool": "search_similar", "status": "start"}

event: tool_result
data: {"tool": "search_similar", "result": "Found 3 agents"}

event: complete
data: {"status": "success"}
```

### Stream Evaluation

```http
GET /api/stream/evaluate/{workflow_id}
```

### Stream Improvement

```http
GET /api/stream/improve/{workflow_id}
```

---

## Error Responses

All endpoints return standard error format:

```json
{
  "detail": "Error message",
  "error_code": "AGENT_NOT_FOUND",
  "status_code": 404
}
```

**Common Status Codes**:
- `200` - Success
- `400` - Invalid request
- `404` - Resource not found
- `500` - Internal server error

---

## Rate Limits

Currently none. Future: 100 requests/minute per IP.

---

## Examples

See `examples/` directory for:
- Python client examples
- curl command examples
- JavaScript fetch examples

---

## Postman Collection

Import `postman_collection.json` for interactive API testing.

---

**For implementation details**: See `docs/ARCHITECTURE.md`  
**For user workflows**: See `docs/USER_GUIDE.md`
