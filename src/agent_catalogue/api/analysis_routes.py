"""Agent analysis routes.

Provides endpoints for analyzing, evaluating, improving, and uploading agent definitions.
All routes use Amplifier agents for LLM-powered operations.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from agent_catalogue.api.models.api_models import (
    AnalyzeResponse,
    CatalogueNeighbor,
    EvaluateResponse,
    ImproveResponse,
    RecheckRequest,
    RecheckResponse,
    RefineRequest,
    RefineResponse,
    UploadResponse,
)
from agent_catalogue.api.utils.analysis_utils import build_metadata
from agent_catalogue.api.utils.diff_utils import compute_diff_sections
from agent_catalogue.api.utils.json_extractor import extract_json, strip_preamble
from agent_catalogue.api.utils.response_formatters import (
    estimate_improved_score,
    grade_label,
    to_token_metrics,
)
from agent_catalogue.models.agent import Agent, AgentSummary, AgentVersion
from agent_catalogue.models.evaluation import QualityEvaluation
from agent_catalogue.models.extraction import ExtractedMetadata
from agent_catalogue.services.comparator import ComparatorService
from agent_catalogue.services.parser import ParserService
from agent_catalogue.services.token_metrics import count_tokens

logger = logging.getLogger(__name__)

router = APIRouter()
_parser = ParserService()
_comparator = ComparatorService()


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
    logger.debug("Extractor response (first 500 chars): %s", extraction_response[:500])
    metadata_dict = extract_json(extraction_response) or {}
    logger.debug(
        "Extracted metadata dict keys: %s", list(metadata_dict.keys()) if metadata_dict else "EMPTY"
    )

    # Build ExtractedMetadata from LLM response with fallbacks
    metadata = build_metadata(metadata_dict, document)

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
    metadata = build_metadata(extract_json(extraction_response) or {}, document)
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
    classification = extract_json(classification_response)
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

    logger.info(
        "POST /api/analyze: similarity detection - content_length=%d, threshold=%.2f",
        content_length,
        similarity_threshold,
    )

    embedding = embedder.embed(content_str)
    similar_with_metadata = db_repo.find_similar_with_metadata(
        embedding, threshold=similarity_threshold, limit=5
    )

    # Build detailed comparisons
    similar_agents = _comparator.build_comparison_results(
        new_metadata=metadata,
        similar_agents=similar_with_metadata,
    )

    # Calculate highest similarity score for early differentiation gate decision
    highest_similarity = max((s.similarity_score for s in similar_agents), default=0.0)
    has_significant_overlap = any(s.comparison.has_significant_overlap for s in similar_agents)

    logger.info("POST /api/analyze: found %d similar agents", len(similar_agents))
    if similar_agents:
        logger.info(
            "POST /api/analyze: highest_similarity=%.2f (early gate triggers at >=0.70)",
            highest_similarity,
        )
        for i, agent in enumerate(similar_agents[:3], 1):
            logger.info(
                "  %d. %s (%.1f%% similar, %d shared capabilities)",
                i,
                agent.agent.name,
                agent.similarity_score * 100,
                len(agent.comparison.capabilities.shared),
            )

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
    logger.info("=" * 80)
    logger.info("POST /api/evaluate: QUALITY ANALYSIS STARTING")
    logger.info("  Content length: %d chars", len(content_str))
    logger.info("  This could be Path A (after differentiation) or Path B (original content)")
    logger.info("=" * 80)

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
    raw = extract_json(eval_response) or {}

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

    logger.info("POST /api/evaluate: Quality evaluation complete")
    logger.info("  Overall score: %.1f/10", score)
    logger.info("  Grade: %s", grade)
    logger.info("  Issues found: %d", len(issues))
    logger.info("=" * 80)
    can_improve = len(issues) > 0

    estimated_score = None
    estimated_grade = None
    if can_improve:
        estimated_score, estimated_grade = estimate_improved_score(raw)

    # Build dimensions dict for frontend
    dimensions: dict[str, Any] = {}
    for dim in raw.get("dimensions", []):
        name = dim.get("dimension", "unknown")
        dimensions[name] = {
            "score": dim.get("score", 5.0),
            "label": ((dim.get("evidence", [""])[0])[:80] if dim.get("evidence") else ""),
        }

    # Token metrics
    token_metrics = to_token_metrics(content_str)

    logger.info("POST /api/evaluate: score=%.1f grade=%s", score, grade)
    return EvaluateResponse(
        overall_score=score,
        grade=grade,
        grade_label=grade_label(grade),
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
    evaluation = extract_json(eval_response) or {}

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
    improved = strip_preamble(improved_raw)

    # Compute section-level diff
    changes = compute_diff_sections(content_str, improved)

    new_score, new_grade = estimate_improved_score(evaluation)
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
        original_token_metrics=to_token_metrics(content_str),
        improved_token_metrics=to_token_metrics(improved),
    )


@router.post("/api/refine")
async def refine_agent_content(
    request: Request,
    body: RefineRequest,
) -> RefineResponse:
    """Refine content to reduce overlap using strategic differentiation.

    Uses the differentiator agent (not improver) which has frameworks for
    niche-carving: narrow scope, different method, adjacent positioning, etc.
    """
    session_mgr = request.app.state.session_mgr
    db_repo = request.app.state.db_repo
    content_str = body.content
    overlapping = body.overlapping_agents

    # Build detailed overlap context with FULL agent content
    agent_ids = [agent.get("id") for agent in overlapping if agent.get("id")]

    # Fetch full agent content for strategic analysis
    full_agents = []
    for agent_id in agent_ids[:3]:  # Limit to top 3 to avoid token explosion
        try:
            agent_uuid = UUID(agent_id)
            agent_summary = db_repo.get_agent(agent_uuid)
            metadata = db_repo.get_agent_metadata(agent_uuid)
            versions = db_repo.get_agent_versions(agent_uuid)
            latest_content = versions[0].raw_content if versions else ""

            full_agents.append(
                {
                    "name": agent_summary.name,
                    "description": agent_summary.description,
                    "capabilities": metadata.get("capabilities", []),
                    "domains": metadata.get("domains", []),
                    "tools": metadata.get("tools", []),
                    "full_content": latest_content[:2000],  # First 2000 chars for context
                }
            )
        except Exception:
            logger.warning("Could not fetch full content for agent %s", agent_id)
            continue

    # Build strategic refinement prompt
    agents_detail = []
    for i, agent in enumerate(full_agents, 1):
        caps = ", ".join(agent["capabilities"][:5]) or "none"
        doms = ", ".join(agent["domains"][:5]) or "none"
        tls = ", ".join(agent["tools"][:5]) or "none"
        agents_detail.append(
            f"{i}. **{agent['name']}**\n"
            f"   Description: {agent['description']}\n"
            f"   Capabilities: {caps}\n"
            f"   Domains: {doms}\n"
            f"   Tools: {tls}\n"
            f"   Content preview: {agent['full_content'][:500]}..."
        )

    agents_text = "\n\n".join(agents_detail)
    token_count = count_tokens(content_str)

    refine_prompt = (
        f"Apply strategic differentiation to reduce overlap.\n\n"
        f"<current_content>\n{content_str}\n</current_content>\n\n"
        f"<overlapping_agents>\n"
        f"These agents overlap significantly. Study their FULL positioning:\n\n"
        f"{agents_text}\n"
        f"</overlapping_agents>\n\n"
        f"Use your differentiation frameworks:\n"
        f"1. **Narrow Scope**: Focus on subset nobody covers deeply\n"
        f"2. **Different Method**: Same problem, different approach\n"
        f"3. **Adjacent Niche**: Related but distinct need\n"
        f"4. **Unique Combo**: Intersection nobody else covers\n"
        f"5. **Different Audience**: Specialize for user segment\n\n"
        f"Apply the MOST APPROPRIATE framework to create clear differentiation.\n\n"
        f"Rules:\n"
        f"- Preserve agent name and core mission\n"
        f"- Be SPECIFIC about what this agent does NOT do\n"
        f"- Add 'Defers to' statements referencing overlapping agents by name\n"
        f"- Remove or reframe any capability that overlaps >50% with existing agents\n"
        f"- Current: {token_count} tokens. Keep under 1500.\n\n"
        f"Output ONLY refined AGENTS.md markdown. No preamble, no code fences."
    )

    # Use differentiator agent (has strategic frameworks), not improver
    try:
        logger.info("=" * 80)
        logger.info(
            "POST /api/refine: EARLY DIFFERENTIATION PATH - User clicked 'Differentiate Now'"
        )
        logger.info("  Calling differentiator agent")
        logger.info("  Prompt length: %d chars", len(refine_prompt))
        logger.info("  Overlapping agents being analyzed: %d", len(full_agents))
        for i, agent in enumerate(full_agents, 1):
            logger.info("    %d. %s", i, agent["name"])

        refined_raw = await session_mgr.run_one_shot("differentiator", refine_prompt)

        logger.info("POST /api/refine: Differentiator response received")
        logger.info("  Length: %d chars", len(refined_raw) if refined_raw else 0)
        logger.info("  First 500 chars: %r", refined_raw[:500] if refined_raw else "EMPTY")
        logger.info(
            "  Last 200 chars: %r",
            refined_raw[-200:] if refined_raw and len(refined_raw) > 200 else refined_raw,
        )
        logger.info("=" * 80)

        if not refined_raw or len(refined_raw.strip()) < 100:
            logger.error("Differentiator returned insufficient output")
            raise HTTPException(
                status_code=500,
                detail="Agent returned empty/invalid response. Check debug log",
            )

        refined = strip_preamble(refined_raw)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Refine failed")
        raise HTTPException(status_code=500, detail=f"Refinement error: {str(e)}") from None

    changes = compute_diff_sections(content_str, refined)
    token_metrics = to_token_metrics(refined)

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
    metadata = build_metadata(
        extract_json(extraction_response) or {},
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
