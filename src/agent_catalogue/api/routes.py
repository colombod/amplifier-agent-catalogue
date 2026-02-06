"""FastAPI routes for Agent Catalogue (Amplifier-powered).

Web routes serve HTML pages via Jinja2 templates.
API routes return JSON. LLM-powered endpoints delegate to the
Amplifier SessionManager instead of calling OpenAI / Copilot directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from agent_catalogue.models.agent import (
    Agent,
    AgentSummary,
    AgentVersion,
    SearchResult,
    SimilarAgent,
    SimilarAgentWithComparison,
)
from agent_catalogue.models.evaluation import QualityEvaluation
from agent_catalogue.models.extraction import ExtractedMetadata
from agent_catalogue.services.comparator import ComparatorService
from agent_catalogue.services.parser import ParserService
from agent_catalogue.services.token_metrics import analyze_tokens, count_tokens

logger = logging.getLogger(__name__)

router = APIRouter()

# Shared service instances (stateless, no config needed)
_parser = ParserService()
_comparator = ComparatorService()


# ---------------------------------------------------------------------------
# JSON helper – extract JSON from LLM prose
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM response text.

    Tries, in order:
    1. JSON inside ```json ... ``` fences
    2. JSON inside ``` ... ``` fences
    3. First balanced { ... } substring
    4. Direct parse of the whole string

    Returns None on failure.
    """
    if not text:
        return None

    stripped = text.strip()

    # 1. ```json code fence
    if "```json" in stripped:
        start = stripped.find("```json") + 7
        end = stripped.find("```", start)
        if end > start:
            candidate = stripped[start:end].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 2. ``` code fence (any language)
    if "```" in stripped:
        start = stripped.find("```") + 3
        # Skip optional language tag on same line
        newline = stripped.find("\n", start)
        if newline != -1:
            start = newline + 1
        end = stripped.find("```", start)
        if end > start:
            candidate = stripped[start:end].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 3. Balanced brace matching
    brace_start = stripped.find("{")
    if brace_start != -1:
        depth = 0
        for i in range(brace_start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[brace_start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    # 4. Whole string
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    logger.warning("Failed to extract JSON from LLM response (%d chars)", len(text))
    return None


def _strip_preamble(text: str) -> str:
    """Strip LLM thinking/commentary before the actual markdown content.

    The model sometimes prepends reasoning or wraps output in code fences.
    This finds the first markdown heading and returns everything from there.
    """
    stripped = text.strip()

    # Strip wrapping code fences (```markdown ... ```)
    if stripped.startswith("```"):
        first_nl = stripped.index("\n") if "\n" in stripped else len(stripped)
        stripped = stripped[first_nl + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()

    # Find the first markdown heading – that is where real content starts
    lines = stripped.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[i:]).strip()

    return stripped.strip()


# ---------------------------------------------------------------------------
# Scoring / diff helpers (pure functions, no LLM)
# ---------------------------------------------------------------------------


def _grade_label(grade: str) -> str:
    """Map letter grade to human-readable label."""
    labels = {
        "A": "Excellent",
        "B": "Good",
        "C": "Adequate",
        "D": "Needs Work",
        "F": "Poor",
    }
    return labels.get(grade, "Unknown")


def _estimate_improved_score(evaluation: dict[str, Any]) -> tuple[float, str]:
    """Estimate what score could be achieved after improvement."""
    current = evaluation.get("overall_score", 5.0)
    issues = evaluation.get("issues", [])
    critical = sum(1 for i in issues if i.get("severity") == "critical")
    major = sum(1 for i in issues if i.get("severity") == "major")

    boost = critical * 1.0 + major * 0.5
    estimated = min(current + boost, 9.5)

    if estimated >= 9.0:
        grade = "A"
    elif estimated >= 7.0:
        grade = "B"
    elif estimated >= 5.0:
        grade = "C"
    elif estimated >= 3.0:
        grade = "D"
    else:
        grade = "F"

    return estimated, grade


def _compute_diff_sections(original: str, improved: str) -> list[dict[str, Any]]:
    """Compute section-level diff between original and improved markdown."""
    heading_re = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)

    def split_sections(text: str) -> list[tuple[str, str]]:
        parts = heading_re.split(text)
        sections: list[tuple[str, str]] = []
        if parts and parts[0].strip():
            sections.append(("(Preamble)", parts[0].strip()))
        for i in range(1, len(parts), 2):
            heading = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append((heading, body))
        return sections

    orig_sections = split_sections(original)
    impr_sections = split_sections(improved)

    orig_map = {h: b for h, b in orig_sections}
    seen_headings: set[str] = set()

    changes: list[dict[str, Any]] = []
    for heading, new_body in impr_sections:
        seen_headings.add(heading)
        old_body = orig_map.get(heading)

        if old_body is None:
            changes.append(
                {
                    "section": heading,
                    "type": "added",
                    "original_lines": [],
                    "improved_lines": new_body.splitlines(),
                }
            )
        elif old_body.strip() == new_body.strip():
            changes.append(
                {
                    "section": heading,
                    "type": "unchanged",
                    "original_lines": old_body.splitlines(),
                    "improved_lines": new_body.splitlines(),
                }
            )
        else:
            changes.append(
                {
                    "section": heading,
                    "type": "modified",
                    "original_lines": old_body.splitlines(),
                    "improved_lines": new_body.splitlines(),
                }
            )

    for heading, body in orig_sections:
        if heading not in seen_headings:
            changes.append(
                {
                    "section": heading,
                    "type": "removed",
                    "original_lines": body.splitlines(),
                    "improved_lines": [],
                }
            )

    return changes


# ---------------------------------------------------------------------------
# Token metrics helper
# ---------------------------------------------------------------------------


class TokenMetrics(BaseModel):
    """Token usage metrics for an AGENTS.md file."""

    total_tokens: int
    total_lines: int
    total_chars: int
    tokens_per_line: float
    budget_category: str  # lean / moderate / heavy / excessive
    budget_label: str
    recommendation: str
    sections: list[dict[str, Any]] = Field(default_factory=list)


def _to_token_metrics(text: str) -> TokenMetrics:
    """Analyze a markdown string and return token metrics."""
    ta = analyze_tokens(text)
    return TokenMetrics(
        total_tokens=ta.total_tokens,
        total_lines=ta.total_lines,
        total_chars=ta.total_chars,
        tokens_per_line=ta.tokens_per_line,
        budget_category=ta.budget_category,
        budget_label=ta.budget_label,
        recommendation=ta.recommendation,
        sections=[
            {
                "heading": s.heading,
                "tokens": s.tokens,
                "pct_of_total": s.pct_of_total,
            }
            for s in ta.sections
        ],
    )


# ===================================================================
# Response Models
# ===================================================================


class UploadResponse(BaseModel):
    """Response from upload endpoint."""

    agent: AgentSummary
    version: int
    similar_agents: list[SimilarAgent]
    is_new: bool


class AnalyzeResponse(BaseModel):
    """Response from analyze endpoint (pre-commit check)."""

    metadata: ExtractedMetadata
    similar_agents: list[SimilarAgentWithComparison]
    content_hash: str
    is_duplicate: bool
    has_significant_overlap: bool = False


class EvaluateResponse(BaseModel):
    """Response from quality evaluation endpoint."""

    overall_score: float
    grade: str
    grade_label: str
    summary: str
    dimensions: dict[str, Any]
    issues: list[dict[str, Any]]
    strengths: list[str]
    can_improve: bool
    estimated_improved_score: float | None = None
    estimated_improved_grade: str | None = None
    token_metrics: TokenMetrics | None = None


class CatalogueNeighbor(BaseModel):
    """An existing agent used as context during improvement."""

    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    similarity_score: float


class ImproveResponse(BaseModel):
    """Response from quality improvement endpoint."""

    improved_content: str
    original_content: str
    changes: list[dict[str, Any]]
    new_score: float | None = None
    new_grade: str | None = None
    improvements_summary: str
    catalogue_neighbors: list[CatalogueNeighbor] = Field(default_factory=list)
    original_token_metrics: TokenMetrics | None = None
    improved_token_metrics: TokenMetrics | None = None


class RefineRequest(BaseModel):
    """Request to refine content to reduce overlap."""

    content: str
    overlapping_agents: list[dict[str, Any]]


class RefineResponse(BaseModel):
    """Response from refinement endpoint."""

    refined_content: str
    original_content: str
    changes: list[dict[str, Any]]
    token_metrics: TokenMetrics | None = None


class RecheckRequest(BaseModel):
    """Request for re-duplication check on improved content."""

    content: str


class RecheckResponse(BaseModel):
    """Response from re-duplication check."""

    similar_agents: list[SimilarAgentWithComparison]
    highest_similarity: float
    has_duplication_risk: bool


# ===================================================================
# Web Routes (HTML)
# ===================================================================


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with agent listing."""
    db_repo = request.app.state.db_repo
    templates = request.app.state.templates
    agents = db_repo.list_agents(limit=50)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "agents": agents, "count": db_repo.count_agents()},
    )


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Upload wizard page."""
    templates = request.app.state.templates
    return templates.TemplateResponse("upload.html", {"request": request})


@router.get("/agent/{slug}", response_class=HTMLResponse)
async def agent_detail(request: Request, slug: str):
    """Agent detail page."""
    db_repo = request.app.state.db_repo
    templates = request.app.state.templates

    agent = db_repo.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    versions = db_repo.get_versions(agent.id)
    current_version = db_repo.get_latest_version(agent.id)

    return templates.TemplateResponse(
        "agent_detail.html",
        {
            "request": request,
            "agent": agent,
            "versions": versions,
            "current_version": current_version,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query(default="", description="Search query"),
):
    """Search page."""
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    templates = request.app.state.templates

    results: list[SearchResult] = []
    if q:
        try:
            query_embedding = embedder.embed(q)
            results = db_repo.search(query_embedding, query_text=q, limit=20)
        except Exception as e:
            logger.error("Search error: %s", e)

    return templates.TemplateResponse(
        "search.html",
        {"request": request, "query": q, "results": results},
    )


@router.get("/download/{slug}")
async def download_by_slug(
    request: Request,
    slug: str,
    version: int | None = Query(default=None),
    format: str = Query(default="md"),
):
    """Download agent by slug (convenience route for web UI)."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await download_agent(request, agent.id, version, format)


@router.post("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    file: Annotated[UploadFile, File()],
    force: bool = Form(default=False),
):
    """Handle form-based upload from web UI."""
    templates = request.app.state.templates
    try:
        result = await upload_agent(request, file, force)
        return RedirectResponse(
            url=f"/agent/{result.agent.slug}",
            status_code=303,
        )
    except HTTPException as e:
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "error": e.detail},
            status_code=e.status_code,
        )


# ===================================================================
# API Routes – Non-LLM (direct DB / embedder)
# ===================================================================


@router.get("/api/agents")
async def list_agents(
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
) -> list[AgentSummary]:
    """List all agents."""
    db_repo = request.app.state.db_repo
    return db_repo.list_agents(limit=limit, offset=offset, search=search)


@router.get("/api/agents/{agent_id}")
async def get_agent(request: Request, agent_id: UUID) -> Agent:
    """Get agent details."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/api/agents/{agent_id}/versions")
async def get_versions(request: Request, agent_id: UUID) -> list[AgentVersion]:
    """Get all versions of an agent."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return db_repo.get_versions(agent_id)


@router.post("/api/search")
async def search_agents(
    request: Request,
    query: Annotated[str, Form(description="Search query")],
    domains: Annotated[list[str] | None, Form()] = None,
    tools: Annotated[list[str] | None, Form()] = None,
    limit: Annotated[int, Form(le=100)] = 20,
) -> list[SearchResult]:
    """Search for agents matching a problem description (vector search)."""
    logger.info("POST /api/search: query=%r", query[:120])
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    query_embedding = embedder.embed(query)
    results = db_repo.search(
        query_embedding,
        query_text=query,
        domains=domains,
        tools=tools,
        limit=limit,
    )
    logger.info("POST /api/search: found %d results", len(results))
    return results


@router.post("/api/similar")
async def find_similar(
    request: Request,
    file: Annotated[UploadFile, File(description="AGENTS.md file")],
    threshold: float = Form(default=0.7, ge=0.0, le=1.0),
) -> list[SimilarAgent]:
    """Find similar agents for a given AGENTS.md file."""
    embedder = request.app.state.embedder
    db_repo = request.app.state.db_repo

    content = await file.read()
    content_str = content.decode("utf-8")
    embedding = embedder.embed(content_str)

    return db_repo.find_similar(embedding, threshold=threshold, limit=10)


@router.delete("/api/agents/{agent_id}")
async def delete_agent(request: Request, agent_id: UUID) -> dict[str, str]:
    """Delete an agent and all its versions."""
    db_repo = request.app.state.db_repo
    if not db_repo.delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": str(agent_id)}


# ===================================================================
# API Routes – Download
# ===================================================================


@router.get("/api/agents/{agent_id}/download")
async def download_agent(
    request: Request,
    agent_id: UUID,
    version: int | None = Query(
        default=None, description="Version number (latest if not specified)"
    ),
    format: str = Query(
        default="md", description="Format: 'md' for raw markdown, 'json' for metadata"
    ),
):
    """Download an agent's AGENTS.md file."""
    db_repo = request.app.state.db_repo
    agent = db_repo.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if version:
        agent_version = db_repo.get_version_by_number(agent_id, version)
    else:
        agent_version = db_repo.get_latest_version(agent_id)

    if not agent_version:
        raise HTTPException(status_code=404, detail="Version not found")

    if format == "json":
        data = {
            "agent": {
                "id": str(agent.id),
                "name": agent.name,
                "slug": agent.slug,
                "description": agent.description,
            },
            "version": {
                "number": agent_version.version_number,
                "created_at": (
                    agent_version.created_at.isoformat() if agent_version.created_at else None
                ),
                "content_hash": agent_version.content_hash,
            },
            "metadata": agent_version.metadata,
            "content": agent_version.raw_content,
        }
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{agent.slug}-v{agent_version.version_number}.json"'
                )
            },
        )

    # Raw markdown
    return Response(
        content=agent_version.raw_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{agent.slug}.md"'},
    )


# ===================================================================
# API Routes – Upload / Store (uses LLM for extraction)
# ===================================================================


@router.post("/api/upload")
async def upload_agent(
    request: Request,
    file: Annotated[UploadFile, File(description="AGENTS.md file to upload")],
    force: bool = Form(default=False, description="Force upload even if similar"),
) -> UploadResponse:
    """Upload and commit an AGENTS.md file to the catalogue."""
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr

    content = await file.read()
    content_str = content.decode("utf-8")
    logger.info("POST /api/upload: content_length=%d", len(content_str))

    # Parse
    document = _parser.parse(content_str)

    # Check for exact duplicate
    existing = db_repo.find_by_content_hash(document.content_hash)
    if existing and not force:
        agent = db_repo.get_agent(existing.agent_id)
        if agent:
            msg = f"Exact duplicate of '{agent.name}' v{existing.version_number}"
            raise HTTPException(status_code=409, detail=msg)

    # Extract metadata via Amplifier
    extraction_response = await session_mgr.run_one_shot(
        "extractor",
        f"Extract structured metadata from this AGENTS.md content. "
        f"Return ONLY valid JSON matching the ExtractedMetadata schema.\n\n{content_str}",
    )
    metadata_dict = _extract_json(extraction_response) or {}

    # Build ExtractedMetadata from LLM response with fallbacks
    metadata = _build_metadata(metadata_dict, document)

    # Generate embedding
    embedding = embedder.embed(content_str)

    # Find similar agents
    similar = db_repo.find_similar(embedding, threshold=0.85, limit=5)

    # Check if agent with this slug exists
    existing_agent = db_repo.get_agent_by_slug(metadata.slug)
    token_count = count_tokens(content_str)

    if existing_agent:
        # Create new version
        version = AgentVersion(
            agent_id=existing_agent.id,
            version_number=0,  # Will be set by repo
            raw_content=content_str,
            content_hash=document.content_hash,
            embedding=embedding,
            metadata=metadata.model_dump(),
            token_count=token_count,
        )
        version = db_repo.create_version(version)

        # Update agent metadata
        existing_agent.description = metadata.description
        db_repo.update_agent(existing_agent)

        return UploadResponse(
            agent=AgentSummary(
                id=existing_agent.id,
                name=existing_agent.name,
                slug=existing_agent.slug,
                description=existing_agent.description,
                version_count=len(db_repo.get_versions(existing_agent.id)),
                current_version=version.version_number,
                domains=metadata.domains,
                capabilities=metadata.capabilities,
                token_count=token_count,
                updated_at=existing_agent.updated_at,
            ),
            version=version.version_number,
            similar_agents=similar,
            is_new=False,
        )

    # Create new agent
    agent = Agent(
        name=metadata.name,
        slug=metadata.slug,
        description=metadata.description,
    )
    agent = db_repo.create_agent(agent)

    version = AgentVersion(
        agent_id=agent.id,
        version_number=1,
        raw_content=content_str,
        content_hash=document.content_hash,
        embedding=embedding,
        metadata=metadata.model_dump(),
        token_count=token_count,
    )
    version = db_repo.create_version(version)

    logger.info("POST /api/upload: stored agent=%s version=%d", agent.name, 1)
    return UploadResponse(
        agent=AgentSummary(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            version_count=1,
            current_version=1,
            domains=metadata.domains,
            capabilities=metadata.capabilities,
            token_count=token_count,
            updated_at=agent.updated_at,
        ),
        version=1,
        similar_agents=similar,
        is_new=True,
    )


# ===================================================================
# API Routes – LLM-Powered Analysis
# ===================================================================


@router.post("/api/analyze")
async def analyze_agent(
    request: Request,
    file: Annotated[UploadFile, File(description="AGENTS.md file to analyze")],
) -> AnalyzeResponse:
    """Analyze an AGENTS.md file without committing.

    Returns extracted metadata and similar agents for review.
    """
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr

    content = await file.read()
    content_str = content.decode("utf-8")
    logger.info("POST /api/analyze: content_length=%d", len(content_str))

    # Parse the document
    document = _parser.parse(content_str)

    # Check for exact duplicate
    existing = db_repo.find_by_content_hash(document.content_hash)
    if existing:
        agent = db_repo.get_agent(existing.agent_id)
        return AnalyzeResponse(
            metadata=ExtractedMetadata(
                name=agent.name if agent else "Unknown",
                slug=agent.slug if agent else "unknown",
                description=agent.description if agent else "",
                purpose="",
            ),
            similar_agents=[],
            content_hash=document.content_hash,
            is_duplicate=True,
        )

    # LLM: extract metadata via Amplifier
    extraction_response = await session_mgr.run_one_shot(
        "extractor",
        f"Extract structured metadata from this AGENTS.md content. "
        f"Return ONLY valid JSON matching the ExtractedMetadata schema.\n\n{content_str}",
    )
    metadata = _build_metadata(_extract_json(extraction_response) or {}, document)
    logger.info(
        "POST /api/analyze: extraction complete, found %d capabilities",
        len(metadata.capabilities),
    )

    # LLM: classify agent via Amplifier
    classification_response = await session_mgr.run_one_shot(
        "classifier",
        f"Classify this agent. Return JSON with: primary_domain, "
        f"secondary_domains, complexity, autonomy, tags.\n\n{content_str}",
    )
    classification = _extract_json(classification_response)
    if classification:
        # Merge classification into metadata where applicable
        if "tags" in classification:
            metadata.keywords = list(set(metadata.keywords + classification.get("tags", [])))
        if "primary_domain" in classification:
            pd = classification["primary_domain"]
            if pd and pd not in metadata.domains:
                metadata.domains = [pd, *metadata.domains]
        if "complexity" in classification and classification["complexity"] in {
            "simple",
            "moderate",
            "complex",
        }:
            metadata.complexity = classification["complexity"]

    # Generate embedding and find similar agents with full metadata
    content_length = len(content_str.strip())
    if content_length < 200:
        similarity_threshold = 0.85
    elif content_length < 500:
        similarity_threshold = 0.75
    else:
        similarity_threshold = 0.6

    embedding = embedder.embed(content_str)
    similar_with_metadata = db_repo.find_similar_with_metadata(
        embedding, threshold=similarity_threshold, limit=5
    )

    # Build detailed comparisons
    similar_agents = _comparator.build_comparison_results(
        new_metadata=metadata,
        similar_agents=similar_with_metadata,
    )

    has_significant_overlap = any(s.comparison.has_significant_overlap for s in similar_agents)
    logger.info("POST /api/analyze: found %d similar agents", len(similar_agents))

    return AnalyzeResponse(
        metadata=metadata,
        similar_agents=similar_agents,
        content_hash=document.content_hash,
        is_duplicate=False,
        has_significant_overlap=has_significant_overlap,
    )


@router.post("/api/evaluate")
async def evaluate_agent_quality(
    request: Request,
    file: Annotated[UploadFile, File(description="AGENTS.md file to evaluate")],
) -> EvaluateResponse:
    """Evaluate the quality of an AGENTS.md file.

    Returns quality scores, grade, issues, and improvement suggestions.
    """
    session_mgr = request.app.state.session_mgr

    content = await file.read()
    content_str = content.decode("utf-8")
    logger.info("POST /api/evaluate: content_length=%d", len(content_str))

    # LLM: evaluate quality via Amplifier
    eval_response = await session_mgr.run_one_shot(
        "evaluator",
        f"Evaluate the quality of this AGENTS.md file.\n\n"
        f"Score across 5 dimensions (clarity, completeness, specificity, "
        f"consistency, differentiation). For each: score 0-10, cite evidence, "
        f"list issues.\n\n"
        f"Calculate overall_score using weights: "
        f"clarity*0.25 + completeness*0.25 + specificity*0.20 "
        f"+ consistency*0.15 + differentiation*0.15\n\n"
        f"Assign grade: A (9-10), B (7-8.9), C (5-6.9), D (3-4.9), F (0-2.9)\n\n"
        f"For each issue: classify severity (critical/major/minor), "
        f"describe problem, identify location, suggest fix.\n\n"
        f"Return JSON with: dimensions (list), overall_score, grade, "
        f"issues (list), strengths (list), summary.\n\n"
        f"<content>\n{content_str}\n</content>",
    )
    raw = _extract_json(eval_response) or {}

    # Parse into validated model with fallbacks
    try:
        evaluation = QualityEvaluation(**raw)
    except Exception:
        evaluation = QualityEvaluation(
            overall_score=raw.get("overall_score", 5.0),
            grade=raw.get("grade", "C"),
            summary=raw.get("summary", ""),
            strengths=raw.get("strengths", []),
        )

    grade = evaluation.grade
    score = evaluation.overall_score
    issues = raw.get("issues", [])
    can_improve = len(issues) > 0

    estimated_score = None
    estimated_grade = None
    if can_improve:
        estimated_score, estimated_grade = _estimate_improved_score(raw)

    # Build dimensions dict for frontend
    dimensions: dict[str, Any] = {}
    for dim in raw.get("dimensions", []):
        name = dim.get("dimension", "unknown")
        dimensions[name] = {
            "score": dim.get("score", 5.0),
            "label": ((dim.get("evidence", [""])[0])[:80] if dim.get("evidence") else ""),
        }

    # Token metrics
    token_metrics = _to_token_metrics(content_str)

    logger.info("POST /api/evaluate: score=%.1f grade=%s", score, grade)
    return EvaluateResponse(
        overall_score=score,
        grade=grade,
        grade_label=_grade_label(grade),
        summary=evaluation.summary or raw.get("summary", ""),
        dimensions=dimensions,
        issues=issues,
        strengths=evaluation.strengths or raw.get("strengths", []),
        can_improve=can_improve,
        estimated_improved_score=estimated_score,
        estimated_improved_grade=estimated_grade,
        token_metrics=token_metrics,
    )


@router.post("/api/improve")
async def improve_agent_quality(
    request: Request,
    file: Annotated[UploadFile, File(description="AGENTS.md file to improve")],
) -> ImproveResponse:
    """Generate an improved version of an AGENTS.md file.

    Fetches similar agents from the catalogue so the LLM can craft
    improvements that complement existing coverage.
    """
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr

    content = await file.read()
    content_str = content.decode("utf-8")
    logger.info("POST /api/improve: content_length=%d", len(content_str))

    # Fetch catalogue neighbors for context-aware improvement
    embedding = embedder.embed(content_str)
    similar_with_metadata = db_repo.find_similar_with_metadata(embedding, threshold=0.3, limit=5)

    catalogue_neighbors: list[CatalogueNeighbor] = []
    catalogue_for_llm: list[dict[str, Any]] = []
    for agent_summary, score, metadata in similar_with_metadata:
        neighbor = CatalogueNeighbor(
            name=agent_summary.name,
            description=agent_summary.description or "",
            capabilities=metadata.get("capabilities", []),
            domains=metadata.get("domains", []),
            tools=metadata.get("tools", []),
            similarity_score=round(score, 3),
        )
        catalogue_neighbors.append(neighbor)
        catalogue_for_llm.append(neighbor.model_dump())

    # Step 1: LLM evaluate quality
    eval_response = await session_mgr.run_one_shot(
        "evaluator",
        f"Evaluate the quality of this AGENTS.md file. "
        f"Return JSON with: overall_score, grade, issues (list with "
        f"severity/description/suggestion), strengths, summary.\n\n"
        f"<content>\n{content_str}\n</content>",
    )
    evaluation = _extract_json(eval_response) or {}

    # Build improvement prompt with catalogue context
    issues_summary = []
    for issue in evaluation.get("issues", []):
        severity = issue.get("severity", "minor")
        desc = issue.get("description", "")
        suggestion = issue.get("suggestion", "")
        issues_summary.append(f"[{severity}] {desc} -> Fix: {suggestion}")

    issues_text = "\n".join(issues_summary) if issues_summary else "No specific issues found."

    catalogue_section = ""
    if catalogue_for_llm:
        neighbor_lines = []
        for i, a in enumerate(catalogue_for_llm, 1):
            caps = ", ".join(a.get("capabilities", [])[:5]) or "none listed"
            doms = ", ".join(a.get("domains", [])[:5]) or "none listed"
            tls = ", ".join(a.get("tools", [])[:5]) or "none listed"
            neighbor_lines.append(
                f"{i}. **{a['name']}** — {a.get('description', 'No description')}\n"
                f"   Capabilities: {caps}\n"
                f"   Domains: {doms}\n"
                f"   Tools: {tls}"
            )
        catalogue_section = (
            "\n<catalogue_context>\n"
            "These agents already exist in the catalogue and cover nearby "
            "functionality.\nThe improved version must NOT duplicate what they "
            "already do.\n\n"
            f"Existing agents:\n{chr(10).join(neighbor_lines)}\n"
            "</catalogue_context>\n"
        )

    original_token_count = count_tokens(content_str)
    token_budget_rule = (
        f"- TOKEN EFFICIENCY: The original is {original_token_count} tokens. "
        "AGENTS.md files are loaded into LLM context at every turn, so every "
        "token matters. Be concise and information-dense. Aim for under 1500 "
        "tokens.\n"
    )

    catalogue_rules = ""
    if catalogue_for_llm:
        catalogue_rules = (
            "- CRITICAL: Differentiate from the catalogue agents above\n"
            "- Carve out a unique niche — emphasize capabilities that NONE "
            "of the existing agents cover\n"
            "- If the original is too vague, sharpen it into a specialist "
            "that fills a gap in the catalogue"
        )

    # Step 2: LLM generate improved version
    improve_prompt = (
        f"Improve this AGENTS.md file based on the quality evaluation.\n\n"
        f"<original_content>\n{content_str}\n</original_content>\n\n"
        f"<evaluation_summary>\n"
        f"Overall score: {evaluation.get('overall_score', 'N/A')}/10 "
        f"(Grade: {evaluation.get('grade', 'N/A')})\n\n"
        f"Issues to address:\n{issues_text}\n"
        f"</evaluation_summary>\n"
        f"{catalogue_section}\n"
        f"Rules:\n"
        f"- Preserve the agent's name, core purpose, and fundamental approach\n"
        f"- Address each issue listed above\n"
        f"- Add missing sections, replace vague language, add examples\n"
        f"- Do NOT invent capabilities not implied by the original\n"
        f"- Maintain the agent's existing voice and tone\n"
        f"{token_budget_rule}{catalogue_rules}\n\n"
        f"IMPORTANT: Your response must start with the first line of the "
        f"improved AGENTS.md. Do NOT include any preamble, thinking, "
        f"explanation, commentary, or code fences.\n"
        f"Output ONLY raw markdown content."
    )

    improved_raw = await session_mgr.run_one_shot("improver", improve_prompt)
    improved = _strip_preamble(improved_raw)

    # Compute section-level diff
    changes = _compute_diff_sections(content_str, improved)

    new_score, new_grade = _estimate_improved_score(evaluation)
    modified = sum(1 for c in changes if c["type"] in ("modified", "added"))
    summary = f"{modified} section(s) improved"

    logger.info("POST /api/improve: improvement complete, %d section(s) changed", modified)
    return ImproveResponse(
        improved_content=improved,
        original_content=content_str,
        changes=changes,
        new_score=new_score,
        new_grade=new_grade,
        improvements_summary=summary,
        catalogue_neighbors=catalogue_neighbors,
        original_token_metrics=_to_token_metrics(content_str),
        improved_token_metrics=_to_token_metrics(improved),
    )


@router.post("/api/refine")
async def refine_agent_content(
    request: Request,
    body: RefineRequest,
) -> RefineResponse:
    """Refine content to reduce overlap with existing agents.

    Takes the current content and a list of overlapping agents,
    rewrites to differentiate more aggressively.
    """
    session_mgr = request.app.state.session_mgr
    content_str = body.content
    overlapping = body.overlapping_agents

    # Build overlap context for LLM
    agent_lines = []
    for i, agent in enumerate(overlapping, 1):
        caps = ", ".join(agent.get("capabilities", [])[:5]) or "none"
        doms = ", ".join(agent.get("domains", [])[:5]) or "none"
        tls = ", ".join(agent.get("tools", [])[:5]) or "none"
        agent_lines.append(
            f"{i}. **{agent['name']}** — "
            f"{agent.get('description', 'No description')}\n"
            f"   Capabilities: {caps}\n"
            f"   Domains: {doms}\n"
            f"   Tools: {tls}"
        )

    agents_text = chr(10).join(agent_lines)
    token_count = count_tokens(content_str)

    refine_prompt = (
        f"Refine this AGENTS.md to reduce overlap with existing agents.\n\n"
        f"<current_content>\n{content_str}\n</current_content>\n\n"
        f"<overlapping_agents>\n"
        f"These agents already exist and overlap with the current definition.\n"
        f"The refined version must CLEARLY DIFFERENTIATE from each.\n\n"
        f"{agents_text}\n</overlapping_agents>\n\n"
        f"Your task:\n"
        f"- Identify which capabilities, domains, or behaviors overlap\n"
        f"- REMOVE or REFRAME overlapping capabilities\n"
        f"- SHARPEN the agent's unique niche\n"
        f"- Add explicit 'Not for' or 'Defers to' statements\n"
        f"- Narrow scope if needed\n\n"
        f"Rules:\n"
        f"- Preserve the agent's name\n"
        f"- Keep the core intent but make it clearly distinct\n"
        f"- Be aggressive about removing overlap\n"
        f"- TOKEN EFFICIENCY: Current version is {token_count} tokens. "
        f"Keep it under 1500 tokens. Be concise.\n\n"
        f"IMPORTANT: Your response must start with the first line of the "
        f"refined AGENTS.md. Do NOT include any preamble, thinking, "
        f"explanation, or code fences.\nOutput ONLY raw markdown content."
    )

    refined_raw = await session_mgr.run_one_shot("improver", refine_prompt)
    refined = _strip_preamble(refined_raw)

    changes = _compute_diff_sections(content_str, refined)
    token_metrics = _to_token_metrics(refined)

    return RefineResponse(
        refined_content=refined,
        original_content=content_str,
        changes=changes,
        token_metrics=token_metrics,
    )


@router.post("/api/analyze-improved")
async def analyze_improved_content(
    request: Request,
    body: RecheckRequest,
) -> RecheckResponse:
    """Re-check improved content for duplication risk.

    Runs similarity search on the improved content to ensure
    improvements haven't made it overlap with existing agents.
    """
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr
    content_str = body.content

    # Generate embedding for improved content
    embedding = embedder.embed(content_str)
    similar_with_metadata = db_repo.find_similar_with_metadata(embedding, threshold=0.6, limit=5)

    if not similar_with_metadata:
        return RecheckResponse(
            similar_agents=[],
            highest_similarity=0.0,
            has_duplication_risk=False,
        )

    # Extract metadata for comparison via Amplifier
    extraction_response = await session_mgr.run_one_shot(
        "extractor",
        f"Extract structured metadata from this AGENTS.md content. "
        f"Return ONLY valid JSON.\n\n{content_str}",
    )
    metadata = _build_metadata(
        _extract_json(extraction_response) or {},
        _parser.parse(content_str),
    )

    # Build detailed comparisons
    similar_agents = _comparator.build_comparison_results(
        new_metadata=metadata,
        similar_agents=similar_with_metadata,
    )

    highest = max((s.similarity_score for s in similar_agents), default=0.0)
    has_risk = any(s.comparison.has_significant_overlap for s in similar_agents)

    return RecheckResponse(
        similar_agents=similar_agents,
        highest_similarity=highest,
        has_duplication_risk=has_risk,
    )


@router.post("/api/compare/{agent_id}")
async def compare_with_agent(
    request: Request,
    agent_id: UUID,
    file: Annotated[UploadFile, File(description="AGENTS.md file to compare")],
):
    """Deep behavioral comparison between uploaded file and existing agent.

    Returns a detailed diff-like comparison using Amplifier agents.
    """
    db_repo = request.app.state.db_repo
    session_mgr = request.app.state.session_mgr

    # Get existing agent
    existing_agent = db_repo.get_agent(agent_id)
    if not existing_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not existing_agent.current_version_id:
        raise HTTPException(status_code=404, detail="Agent has no versions")

    existing_version = db_repo.get_version(existing_agent.current_version_id)
    if not existing_version:
        raise HTTPException(status_code=404, detail="Agent version not found")

    # Read uploaded content
    new_content = (await file.read()).decode("utf-8")
    new_document = _parser.parse(new_content)
    new_name = new_document.title or "Uploaded Agent"

    # LLM: compare agents via Amplifier
    compare_prompt = (
        f"Compare these two AGENTS.md files and produce a behavioral diff.\n\n"
        f'<agent_a name="{new_name}">\n{new_content}\n</agent_a>\n\n'
        f'<agent_b name="{existing_agent.name}">\n'
        f"{existing_version.raw_content}\n</agent_b>\n\n"
        f"Return JSON with:\n"
        f'- verdict: "distinct", "overlapping", or "duplicate"\n'
        f"- similarity_score: 0.0 to 1.0\n"
        f'- capability_diff: {{"shared": [], "unique_to_a": [], "unique_to_b": []}}\n'
        f"- behavioral_diff: object describing differences\n"
        f'- recommendation: {{"action": "keep_both"|"merge"|"replace", '
        f'"reasoning": "..."}}\n\n'
        f"Output ONLY valid JSON."
    )

    compare_response = await session_mgr.run_one_shot("analyzer", compare_prompt)
    comparison = _extract_json(compare_response) or {}

    # LLM: generate narrative
    narrate_prompt = (
        f"Generate a clear narrative explaining this agent comparison.\n\n"
        f'Agent names: "{new_name}" vs "{existing_agent.name}"\n\n'
        f"<comparison_data>\n{json.dumps(comparison, indent=2)}\n"
        f"</comparison_data>\n\n"
        f"Write a clear explanation covering:\n"
        f"1. The verdict and what it means\n"
        f"2. What the agents share\n"
        f"3. Key differences\n"
        f"4. Your recommendation\n"
        f"5. If keeping both, how to choose between them\n\n"
        f"Output ONLY the narrative text, no JSON, no markdown headers."
    )

    narrative = await session_mgr.run_one_shot("analyzer", narrate_prompt)

    return {
        "comparison": comparison,
        "narrative": narrative,
        "new_agent": new_name,
        "existing_agent": existing_agent.name,
    }


@router.post("/api/search-agent")
async def search_with_agent(
    request: Request,
    query: Annotated[str, Form(description="Natural language search query")],
) -> dict[str, Any]:
    """Search using HyDE (Hypothetical Document Embedding).

    Bridges the linguistic gap between user intent and agent descriptions.
    Step 1: LLM generates a hypothetical agent description matching the query
    Step 2: Embed that description and vector search
    Step 3: LLM explains why each result is relevant
    """
    logger.info("POST /api/search-agent: query=%r", query[:120])
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr

    # Step 1: Generate hypothetical agent description
    hyde_prompt = (
        f'A user is searching an AI agent catalogue with:\n\n"{query}"\n\n'
        f"Write a SHORT hypothetical AGENTS.md description (3-5 sentences) "
        f"of an agent that would perfectly match this query. Write it as "
        f"capability statements, NOT as a question. Use the same language "
        f"patterns that real agent definitions use.\n\n"
        f"Output ONLY the hypothetical description, nothing else."
    )

    hypothetical_doc = await session_mgr.run_one_shot("analyzer", hyde_prompt)

    # Step 2: Embed the hypothetical doc and vector search
    embedding = embedder.embed(hypothetical_doc)
    results = db_repo.find_similar_with_metadata(
        embedding=embedding,
        threshold=0.3,
        limit=10,
    )

    if not results:
        return {
            "results": [],
            "hypothetical_doc": hypothetical_doc.strip(),
            "total_found": 0,
        }

    # Step 3: LLM explains relevance of each result
    agents_text = "\n".join(f"- {s.name}: {s.description}" for s, _, _ in results)
    explain_prompt = (
        f'User asked: "{query}"\n\n'
        f"These agents were found:\n{agents_text}\n\n"
        f"For each agent, write ONE sentence explaining why it's relevant. "
        f"If an agent is NOT relevant, mark it as irrelevant.\n\n"
        f"Return JSON array:\n"
        f'[{{"name": "Name", "explanation": "Why relevant", "relevant": true}}]\n\n'
        f"Output ONLY valid JSON, no code blocks."
    )

    explain_response = await session_mgr.run_one_shot("analyzer", explain_prompt)
    explanations_raw = _extract_json(explain_response)

    # Handle both list and dict responses
    if isinstance(explanations_raw, dict):
        explanations_list: list[Any] = explanations_raw.get("results", [])
    elif isinstance(explanations_raw, list):
        explanations_list = explanations_raw
    else:
        explanations_list = []

    explanations: dict[str, dict[str, Any]] = {}
    for e in explanations_list:
        if isinstance(e, dict):
            explanations[e.get("name", "")] = e

    # Build response, filtering irrelevant results
    search_results = []
    for summary, score, metadata in results:
        exp = explanations.get(summary.name, {})
        if exp.get("relevant") is False:
            continue
        search_results.append(
            {
                "agent_id": str(summary.id),
                "name": summary.name,
                "slug": summary.slug,
                "description": summary.description,
                "relevance_score": round(score, 3),
                "explanation": exp.get("explanation", ""),
                "domains": metadata.get("domains", []),
                "capabilities": metadata.get("capabilities", [])[:5],
                "token_count": summary.token_count,
            }
        )

    logger.info("POST /api/search-agent: found %d results", len(search_results))
    return {
        "results": search_results,
        "hypothetical_doc": hypothetical_doc.strip(),
        "total_found": len(search_results),
    }


# ===================================================================
# SSE Streaming Endpoints (real-time Amplifier events)
# ===================================================================


@router.post("/api/stream/evaluate")
async def stream_evaluate(request: Request) -> StreamingResponse:
    """SSE streaming version of evaluate - shows real-time agent reasoning.

    Emits kernel events (thinking, tool calls) as they happen, then
    sends the final result in a 'result' event.
    """
    body = await request.json()
    content_str = body.get("content", "")
    if not content_str:
        raise HTTPException(status_code=400, detail="content is required")

    session_mgr = request.app.state.session_mgr
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        await queue.put({"event": event, "data": data})

    async def run() -> None:
        try:
            # Phase: evaluating
            await _emit(
                "phase",
                {
                    "phase": "evaluating",
                    "message": "Evaluator agent analyzing quality...",
                    "agent_name": "evaluator",
                },
            )

            eval_response = await session_mgr.run_one_shot_streaming(
                "evaluator",
                f"Evaluate the quality of this AGENTS.md file.\n\n"
                f"Score across 5 dimensions (clarity, completeness, specificity, "
                f"consistency, differentiation). For each: score 0-10, cite evidence, "
                f"list issues.\n\n"
                f"Calculate overall_score using weights: "
                f"clarity*0.25 + completeness*0.25 + specificity*0.20 "
                f"+ consistency*0.15 + differentiation*0.15\n\n"
                f"Assign grade: A (9-10), B (7-8.9), C (5-6.9), D (3-4.9), F (0-2.9)\n\n"
                f"For each issue: classify severity (critical/major/minor), "
                f"describe problem, identify location, suggest fix.\n\n"
                f"Return JSON with: dimensions (list), overall_score, grade, "
                f"issues (list), strengths (list), summary.\n\n"
                f"<content>\n{content_str}\n</content>",
                queue,
            )

            raw = _extract_json(eval_response) or {}

            # Parse into validated model with fallbacks
            try:
                evaluation = QualityEvaluation(**raw)
            except Exception:
                evaluation = QualityEvaluation(
                    overall_score=raw.get("overall_score", 5.0),
                    grade=raw.get("grade", "C"),
                    summary=raw.get("summary", ""),
                    strengths=raw.get("strengths", []),
                )

            grade = evaluation.grade
            score = evaluation.overall_score
            issues = raw.get("issues", [])
            can_improve = len(issues) > 0

            estimated_score = None
            estimated_grade = None
            if can_improve:
                estimated_score, estimated_grade = _estimate_improved_score(raw)

            # Build dimensions dict for frontend
            dimensions: dict[str, Any] = {}
            for dim in raw.get("dimensions", []):
                name = dim.get("dimension", "unknown")
                dimensions[name] = {
                    "score": dim.get("score", 5.0),
                    "label": ((dim.get("evidence", [""])[0])[:80] if dim.get("evidence") else ""),
                }

            token_metrics = _to_token_metrics(content_str)

            await _emit(
                "result",
                {
                    "result": EvaluateResponse(
                        overall_score=score,
                        grade=grade,
                        grade_label=_grade_label(grade),
                        summary=evaluation.summary or raw.get("summary", ""),
                        dimensions=dimensions,
                        issues=issues,
                        strengths=evaluation.strengths or raw.get("strengths", []),
                        can_improve=can_improve,
                        estimated_improved_score=estimated_score,
                        estimated_improved_grade=estimated_grade,
                        token_metrics=token_metrics,
                    ).model_dump()
                },
            )

        except Exception as e:
            logger.exception("SSE evaluate failed")
            await _emit("error", {"message": str(e)})
        finally:
            await queue.put(None)

    asyncio.create_task(run())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            event_type = item.get("event", "message")
            payload = json.dumps(item.get("data", {}))
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/stream/improve")
async def stream_improve(request: Request) -> StreamingResponse:
    """SSE streaming version of improve - shows real-time agent reasoning.

    Three phases:
    1. Finding similar agents in catalogue (embedding + DB)
    2. Evaluator agent assessing quality (LLM)
    3. Improver agent generating enhanced version (LLM)
    """
    body = await request.json()
    content_str = body.get("content", "")
    if not content_str:
        raise HTTPException(status_code=400, detail="content is required")

    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        await queue.put({"event": event, "data": data})

    async def run() -> None:
        try:
            # --- Phase 1: catalogue lookup (non-LLM) ---
            await _emit(
                "phase",
                {
                    "phase": "catalogue",
                    "message": "Finding similar agents in catalogue...",
                },
            )

            embedding = embedder.embed(content_str)
            similar_with_metadata = db_repo.find_similar_with_metadata(
                embedding, threshold=0.3, limit=5
            )

            catalogue_neighbors: list[CatalogueNeighbor] = []
            for agent_summary, sim_score, metadata in similar_with_metadata:
                neighbor = CatalogueNeighbor(
                    name=agent_summary.name,
                    description=agent_summary.description or "",
                    capabilities=metadata.get("capabilities", []),
                    domains=metadata.get("domains", []),
                    tools=metadata.get("tools", []),
                    similarity_score=round(sim_score, 3),
                )
                catalogue_neighbors.append(neighbor)

            # --- Phase 2: evaluate (LLM) ---
            await _emit(
                "phase",
                {
                    "phase": "evaluating",
                    "message": "Evaluator agent assessing quality...",
                    "agent_name": "evaluator",
                },
            )

            eval_response = await session_mgr.run_one_shot_streaming(
                "evaluator",
                f"Evaluate the quality of this AGENTS.md file. "
                f"Return JSON with: overall_score, grade, issues (list with "
                f"severity/description/suggestion), strengths, summary.\n\n"
                f"<content>\n{content_str}\n</content>",
                queue,
            )
            evaluation = _extract_json(eval_response) or {}

            # Build improvement prompt with catalogue context
            issues_summary = []
            for issue in evaluation.get("issues", []):
                severity = issue.get("severity", "minor")
                desc = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                issues_summary.append(f"[{severity}] {desc} -> Fix: {suggestion}")

            issues_text = (
                "\n".join(issues_summary) if issues_summary else "No specific issues found."
            )

            original_token_count = count_tokens(content_str)

            # --- Phase 3: improve (LLM with tools) ---
            await _emit(
                "phase",
                {
                    "phase": "improving",
                    "message": "Improver agent researching catalogue and improving...",
                    "agent_name": "improver",
                },
            )

            improve_prompt = (
                f"Improve this AGENTS.md definition based on the quality evaluation below.\n\n"
                f"<original_content>\n{content_str}\n</original_content>\n\n"
                f"<evaluation_summary>\n"
                f"Overall score: {evaluation.get('overall_score', 'N/A')}/10 "
                f"(Grade: {evaluation.get('grade', 'N/A')})\n\n"
                f"Issues to address:\n{issues_text}\n"
                f"</evaluation_summary>\n\n"
                f"You have access to tools:\n"
                f"- search_similar: Search the agent catalogue for similar agents\n"
                f"- get_agent_content: Read the full AGENTS.md of a specific agent\n\n"
                f"Use these tools to understand the landscape of existing agents, "
                f"then generate an improved version that:\n"
                f"1. Fixes all identified quality issues\n"
                f"2. Differentiates from similar agents you find in the catalogue\n"
                f"3. Carves out a unique niche\n\n"
                f"Original token count: {original_token_count}. Aim for under 1500 tokens.\n\n"
                f"Output ONLY the improved raw markdown. No preamble, no code fences."
            )

            improved_raw = await session_mgr.run_one_shot_streaming(
                "improver", improve_prompt, queue
            )
            improved = _strip_preamble(improved_raw)

            # Compute section-level diff
            changes = _compute_diff_sections(content_str, improved)

            new_score, new_grade = _estimate_improved_score(evaluation)
            modified = sum(1 for c in changes if c["type"] in ("modified", "added"))
            summary = f"{modified} section(s) improved"

            await _emit(
                "result",
                {
                    "result": ImproveResponse(
                        improved_content=improved,
                        original_content=content_str,
                        changes=changes,
                        new_score=new_score,
                        new_grade=new_grade,
                        improvements_summary=summary,
                        catalogue_neighbors=catalogue_neighbors,
                        original_token_metrics=_to_token_metrics(content_str),
                        improved_token_metrics=_to_token_metrics(improved),
                    ).model_dump()
                },
            )

        except Exception as e:
            logger.exception("SSE improve failed")
            await _emit("error", {"message": str(e)})
        finally:
            await queue.put(None)

    asyncio.create_task(run())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            event_type = item.get("event", "message")
            payload = json.dumps(item.get("data", {}))
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/stream/search-agent")
async def stream_search_agent(request: Request) -> StreamingResponse:
    """SSE streaming version of search-agent - shows real-time HyDE reasoning.

    Three phases:
    1. Generating hypothetical agent description (LLM - HyDE)
    2. Searching catalogue with vector similarity (embedding + DB)
    3. Analyzing relevance of results (LLM)
    """
    body = await request.json()
    query = body.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    logger.info("POST /api/stream/search-agent: query=%r", query[:120])
    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        await queue.put({"event": event, "data": data})

    async def run() -> None:
        try:
            # --- Phase 1: HyDE generation (LLM) ---
            await _emit(
                "phase",
                {
                    "phase": "hyde",
                    "message": "Analyzer agent generating hypothetical agent description...",
                    "agent_name": "analyzer",
                },
            )

            hyde_prompt = (
                f'A user is searching an AI agent catalogue with:\n\n"{query}"\n\n'
                f"Write a SHORT hypothetical AGENTS.md description (3-5 sentences) "
                f"of an agent that would perfectly match this query. Write it as "
                f"capability statements, NOT as a question. Use the same language "
                f"patterns that real agent definitions use.\n\n"
                f"Output ONLY the hypothetical description, nothing else."
            )

            hypothetical_doc = await session_mgr.run_one_shot_streaming(
                "analyzer", hyde_prompt, queue
            )

            # --- Phase 2: vector search (non-LLM) ---
            await _emit(
                "phase",
                {
                    "phase": "searching",
                    "message": "Searching catalogue with vector similarity...",
                },
            )

            embedding = embedder.embed(hypothetical_doc)
            results = db_repo.find_similar_with_metadata(
                embedding=embedding,
                threshold=0.3,
                limit=10,
            )

            if not results:
                await _emit(
                    "result",
                    {
                        "result": {
                            "results": [],
                            "hypothetical_doc": hypothetical_doc.strip(),
                            "total_found": 0,
                        }
                    },
                )
                return

            # --- Phase 3: explain relevance (LLM) ---
            await _emit(
                "phase",
                {
                    "phase": "explaining",
                    "message": "Analyzer agent explaining relevance of results...",
                    "agent_name": "analyzer",
                },
            )

            agents_text = "\n".join(f"- {s.name}: {s.description}" for s, _, _ in results)
            explain_prompt = (
                f'User asked: "{query}"\n\n'
                f"These agents were found:\n{agents_text}\n\n"
                f"For each agent, write ONE sentence explaining why it's relevant. "
                f"If an agent is NOT relevant, mark it as irrelevant.\n\n"
                f"Return JSON array:\n"
                f'[{{"name": "Name", "explanation": "Why relevant", "relevant": true}}]\n\n'
                f"Output ONLY valid JSON, no code blocks."
            )

            explain_response = await session_mgr.run_one_shot_streaming(
                "analyzer", explain_prompt, queue
            )
            explanations_raw = _extract_json(explain_response)

            # Handle both list and dict responses
            if isinstance(explanations_raw, dict):
                explanations_list: list[Any] = explanations_raw.get("results", [])
            elif isinstance(explanations_raw, list):
                explanations_list = explanations_raw
            else:
                explanations_list = []

            explanations: dict[str, dict[str, Any]] = {}
            for e in explanations_list:
                if isinstance(e, dict):
                    explanations[e.get("name", "")] = e

            # Build response, filtering irrelevant results
            search_results = []
            for summary, sim_score, metadata in results:
                exp = explanations.get(summary.name, {})
                if exp.get("relevant") is False:
                    continue
                search_results.append(
                    {
                        "agent_id": str(summary.id),
                        "name": summary.name,
                        "slug": summary.slug,
                        "description": summary.description,
                        "relevance_score": round(sim_score, 3),
                        "explanation": exp.get("explanation", ""),
                        "domains": metadata.get("domains", []),
                        "capabilities": metadata.get("capabilities", [])[:5],
                        "token_count": summary.token_count,
                    }
                )

            await _emit(
                "result",
                {
                    "result": {
                        "results": search_results,
                        "hypothetical_doc": hypothetical_doc.strip(),
                        "total_found": len(search_results),
                    }
                },
            )

        except Exception as e:
            logger.exception("SSE search-agent failed")
            await _emit("error", {"message": str(e)})
        finally:
            await queue.put(None)

    asyncio.create_task(run())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            event_type = item.get("event", "message")
            payload = json.dumps(item.get("data", {}))
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ===================================================================
# SSE Streaming Endpoint (analyze)
# ===================================================================


@router.post("/api/stream/analyze")
async def stream_analyze(request: Request):
    """SSE streaming version of analyze.

    Creates a workflow session, runs analysis steps, and streams
    progress events to the client via Server-Sent Events.
    """
    body = await request.json()
    content_str = body.get("content", "")
    if not content_str:
        raise HTTPException(status_code=400, detail="content is required")

    db_repo = request.app.state.db_repo
    embedder = request.app.state.embedder
    session_mgr = request.app.state.session_mgr

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        """Put an SSE event on the queue."""
        await queue.put({"event": event, "data": data})

    async def run_analysis() -> None:
        try:
            # --- Parse (non-LLM) ---
            await _emit("step", {"name": "parse", "status": "running"})
            document = _parser.parse(content_str)

            # Duplicate check
            existing = db_repo.find_by_content_hash(document.content_hash)
            if existing:
                agent = db_repo.get_agent(existing.agent_id)
                await _emit(
                    "duplicate",
                    {
                        "agent_name": agent.name if agent else "Unknown",
                        "content_hash": document.content_hash,
                    },
                )
                return

            await _emit("step", {"name": "parse", "status": "done"})

            # --- Extract metadata (LLM) ---
            await _emit("step", {"name": "extract", "status": "running"})
            extraction_response = await session_mgr.run_one_shot(
                "extractor",
                f"Extract structured metadata from this AGENTS.md content. "
                f"Return ONLY valid JSON.\n\n{content_str}",
            )
            metadata = _build_metadata(_extract_json(extraction_response) or {}, document)
            await _emit(
                "step",
                {
                    "name": "extract",
                    "status": "done",
                    "metadata": metadata.model_dump(),
                },
            )

            # --- Classify (LLM) ---
            await _emit("step", {"name": "classify", "status": "running"})
            classification_response = await session_mgr.run_one_shot(
                "classifier",
                f"Classify this agent. Return JSON with: primary_domain, "
                f"secondary_domains, complexity, autonomy, tags.\n\n{content_str}",
            )
            classification = _extract_json(classification_response)
            if classification:
                if "tags" in classification:
                    metadata.keywords = list(
                        set(metadata.keywords + classification.get("tags", []))
                    )
                if "primary_domain" in classification:
                    pd = classification["primary_domain"]
                    if pd and pd not in metadata.domains:
                        metadata.domains = [pd, *metadata.domains]
            await _emit("step", {"name": "classify", "status": "done"})

            # --- Embedding + similarity (non-LLM) ---
            await _emit("step", {"name": "similarity", "status": "running"})
            content_length = len(content_str.strip())
            if content_length < 200:
                threshold = 0.85
            elif content_length < 500:
                threshold = 0.75
            else:
                threshold = 0.6

            embedding = embedder.embed(content_str)
            similar_with_metadata = db_repo.find_similar_with_metadata(
                embedding, threshold=threshold, limit=5
            )

            similar_agents = _comparator.build_comparison_results(
                new_metadata=metadata,
                similar_agents=similar_with_metadata,
            )
            await _emit(
                "step",
                {
                    "name": "similarity",
                    "status": "done",
                    "similar_count": len(similar_agents),
                },
            )

            # --- Final result ---
            has_overlap = any(s.comparison.has_significant_overlap for s in similar_agents)
            await _emit(
                "result",
                {
                    "metadata": metadata.model_dump(),
                    "similar_agents": [s.model_dump() for s in similar_agents],
                    "content_hash": document.content_hash,
                    "is_duplicate": False,
                    "has_significant_overlap": has_overlap,
                },
            )

        except Exception as e:
            logger.exception("SSE analysis failed")
            await queue.put(
                {
                    "event": "error",
                    "data": {"message": str(e)},
                }
            )
        finally:
            # Signal end of stream
            await queue.put(None)

    # Fire and forget
    asyncio.create_task(run_analysis())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            event_type = item.get("event", "message")
            payload = json.dumps(item.get("data", {}))
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ===================================================================
# Internal Helpers
# ===================================================================


def _build_metadata(
    data: dict[str, Any],
    document: Any,
) -> ExtractedMetadata:
    """Build ExtractedMetadata from an LLM-extracted dict with fallbacks.

    Args:
        data: Dict parsed from LLM JSON output.
        document: ParsedDocument for fallback values (title, etc.).
    """
    name = data.get("name") or getattr(document, "title", None) or "Unknown Agent"
    slug = _generate_slug(data.get("slug") or name)

    def _ensure_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            return [value] if value else []
        return []

    complexity_val = data.get("complexity", "moderate")
    if complexity_val not in {"simple", "moderate", "complex"}:
        complexity_val = "moderate"

    autonomy_val = data.get("autonomy", "hybrid")
    if autonomy_val not in {"autonomous", "guided", "hybrid"}:
        autonomy_val = "hybrid"

    return ExtractedMetadata(
        name=name,
        slug=slug,
        description=data.get("description", ""),
        purpose=data.get("purpose", ""),
        capabilities=_ensure_list(data.get("capabilities", [])),
        domains=_ensure_list(data.get("domains", [])),
        tools=_ensure_list(data.get("tools", [])),
        behaviors=_ensure_list(data.get("behaviors", [])),
        triggers=_ensure_list(data.get("triggers", [])),
        complexity=complexity_val,
        autonomy=autonomy_val,
        keywords=_ensure_list(data.get("keywords", [])),
        summary=data.get("summary", ""),
    )


def _generate_slug(name: str) -> str:
    """Generate URL-safe slug from name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-") or "unknown"
