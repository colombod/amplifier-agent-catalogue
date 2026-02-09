"""SSE streaming routes for real-time Amplifier agent events.

Provides Server-Sent Events (SSE) endpoints that stream kernel events
(tool calls, thinking blocks, provider calls) as they happen during
LLM agent execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent_catalogue.api.models.api_models import (
    CatalogueNeighbor,
    EvaluateResponse,
    ImproveResponse,
)
from agent_catalogue.api.utils.analysis_utils import build_metadata
from agent_catalogue.api.utils.diff_utils import compute_diff_sections
from agent_catalogue.api.utils.json_extractor import extract_json, strip_preamble
from agent_catalogue.api.utils.response_formatters import (
    estimate_improved_score,
    grade_label,
    to_token_metrics,
)
from agent_catalogue.models.evaluation import QualityEvaluation
from agent_catalogue.services.comparator import ComparatorService
from agent_catalogue.services.parser import ParserService
from agent_catalogue.services.token_metrics import count_tokens

logger = logging.getLogger(__name__)

router = APIRouter()
_parser = ParserService()
_comparator = ComparatorService()


@router.post("/api/stream/analyze")
async def stream_analyze_agent(
    request: Request,
) -> StreamingResponse:
    """SSE streaming version of analyze - shows real-time agent reasoning.

    Three phases:
    1. Parse and check for duplicates (fast, no LLM)
    2. Extractor agent extracting metadata (LLM)
    3. Classifier agent classifying domains/tags (LLM)
    4. Find similar agents and build comparisons (fast)
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
            # Phase 1: Parse and check duplicates
            await _emit(
                "phase",
                {
                    "phase": "parsing",
                    "message": "Parsing document and checking for duplicates...",
                },
            )

            document = _parser.parse(content_str)
            existing = db_repo.find_by_content_hash(document.content_hash)

            if existing:
                agent = db_repo.get_agent(existing.agent_id)
                await _emit(
                    "result",
                    {
                        "metadata": {
                            "name": agent.name if agent else "Unknown",
                            "slug": agent.slug if agent else "unknown",
                            "description": agent.description if agent else "",
                            "purpose": "",
                        },
                        "similar_agents": [],
                        "content_hash": document.content_hash,
                        "is_duplicate": True,
                        "has_significant_overlap": False,
                    },
                )
                return

            # Phase 2: Extract metadata
            await _emit(
                "phase",
                {
                    "phase": "extracting",
                    "message": "Extractor agent analyzing structure and capabilities...",
                    "agent_name": "extractor",
                },
            )

            extraction_response = await session_mgr.run_one_shot_streaming(
                "extractor",
                f"Extract structured metadata from this AGENTS.md content. "
                f"Return ONLY valid JSON matching the ExtractedMetadata schema.\n\n{content_str}",
                queue,
            )
            metadata = build_metadata(extract_json(extraction_response) or {}, document)
            logger.info(
                "Stream analyze: extraction complete, found %d capabilities",
                len(metadata.capabilities),
            )

            # Phase 3: Classify agent
            await _emit(
                "phase",
                {
                    "phase": "classifying",
                    "message": "Classifier agent determining domains and tags...",
                    "agent_name": "classifier",
                },
            )

            classification_response = await session_mgr.run_one_shot_streaming(
                "classifier",
                f"Classify this agent. Return JSON with: primary_domain, "
                f"secondary_domains, complexity, autonomy, tags.\n\n{content_str}",
                queue,
            )
            classification = extract_json(classification_response)

            if classification:
                # Merge classification into metadata
                if "tags" in classification:
                    metadata.keywords = list(
                        set(metadata.keywords + classification.get("tags", []))
                    )
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

            # Phase 4: Find similar agents
            await _emit(
                "phase",
                {
                    "phase": "finding_similar",
                    "message": "Searching for similar agents in catalogue...",
                },
            )

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

            # Phase 5: Build comparisons
            await _emit(
                "phase",
                {
                    "phase": "building_comparisons",
                    "message": "Analyzing overlaps and differences...",
                },
            )

            similar_agents = _comparator.build_comparison_results(
                new_metadata=metadata,
                similar_agents=similar_with_metadata,
            )

            highest_similarity = max((s.similarity_score for s in similar_agents), default=0.0)
            has_significant_overlap = any(
                s.comparison.has_significant_overlap for s in similar_agents
            )

            logger.info("Stream analyze: found %d similar agents", len(similar_agents))
            if similar_agents:
                logger.info(
                    "Stream analyze: highest_similarity=%.2f",
                    highest_similarity,
                )

            # Emit final result
            await _emit(
                "result",
                {
                    "metadata": {
                        "name": metadata.name,
                        "slug": metadata.slug,
                        "description": metadata.description,
                        "purpose": metadata.purpose,
                        "capabilities": metadata.capabilities,
                        "domains": metadata.domains,
                        "keywords": metadata.keywords,
                        "complexity": metadata.complexity,
                        "autonomy": metadata.autonomy,
                        "tools": metadata.tools,
                        "behaviors": metadata.behaviors,
                        "triggers": metadata.triggers,
                    },
                    "similar_agents": [
                        {
                            "agent": {
                                "id": str(s.agent.id),
                                "name": s.agent.name,
                                "description": s.agent.description,
                                "capabilities": s.agent.capabilities,
                                "domains": s.agent.domains,
                            },
                            "similarity_score": s.similarity_score,
                            "comparison": {
                                "has_significant_overlap": s.comparison.has_significant_overlap,
                                "capabilities": {
                                    "shared": s.comparison.capabilities.shared,
                                    "only_in_new": s.comparison.capabilities.only_in_new,
                                    "only_in_existing": s.comparison.capabilities.only_in_existing,
                                },
                            },
                        }
                        for s in similar_agents
                    ],
                    "content_hash": document.content_hash,
                    "is_duplicate": False,
                    "has_significant_overlap": has_significant_overlap,
                },
            )

        except Exception as e:
            logger.exception("SSE analyze failed")
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

            token_metrics = to_token_metrics(content_str)

            await _emit(
                "result",
                {
                    "result": EvaluateResponse(
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
    2. Evaluator agent assessing quality (LLM) - OPTIONAL if evaluation provided
    3. Improver agent generating enhanced version (LLM)
    """
    body = await request.json()
    content_str = body.get("content", "")
    provided_evaluation = body.get("evaluation")  # May be passed from Step 4
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

            # --- Phase 2: evaluate (LLM) - SKIP if evaluation provided ---
            if provided_evaluation:
                logger.info("Using provided evaluation from Step 4 (skipping evaluator)")
                evaluation = provided_evaluation
            else:
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
                evaluation = extract_json(eval_response) or {}

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
            improved = strip_preamble(improved_raw)

            # Compute section-level diff
            changes = compute_diff_sections(content_str, improved)

            new_score, new_grade = estimate_improved_score(evaluation)
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
                        original_token_metrics=to_token_metrics(content_str),
                        improved_token_metrics=to_token_metrics(improved),
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
