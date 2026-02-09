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
    workflow_id = body.get("workflow_id")  # Optional for sticky sessions

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

            # Use sticky session if workflow_id provided (context accumulates)
            extraction_prompt = (
                f"Extract structured metadata from this AGENTS.md content. "
                f"Return ONLY valid JSON matching the ExtractedMetadata schema.\n\n{content_str}"
            )

            if workflow_id:
                extraction_response = await session_mgr.run_with_sticky_session(
                    workflow_id, "extractor", extraction_prompt, queue
                )
            else:
                extraction_response = await session_mgr.run_one_shot_streaming(
                    "extractor", extraction_prompt, queue
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

            classification_prompt = (
                f"Classify this agent. Return JSON with: primary_domain, "
                f"secondary_domains, complexity, autonomy, tags.\n\n{content_str}"
            )

            if workflow_id:
                classification_response = await session_mgr.run_with_sticky_session(
                    workflow_id, "classifier", classification_prompt, queue
                )
            else:
                classification_response = await session_mgr.run_one_shot_streaming(
                    "classifier", classification_prompt, queue
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

            # Store similarity data in workflow metadata for later stages
            if workflow_id:
                session_mgr.set_workflow_metadata(
                    workflow_id,
                    "similar_agents",
                    [
                        {
                            "id": str(s.agent.id),
                            "name": s.agent.name,
                            "description": s.agent.description,
                            "similarity_score": s.similarity_score,
                            "shared_capabilities": s.comparison.capabilities.shared,
                            "unique_capabilities": s.comparison.capabilities.only_in_new,
                            "has_overlap": s.comparison.has_significant_overlap,
                        }
                        for s in similar_agents
                    ],
                )
                session_mgr.set_workflow_metadata(
                    workflow_id, "highest_similarity", highest_similarity
                )
                session_mgr.set_workflow_metadata(
                    workflow_id, "has_significant_overlap", has_significant_overlap
                )
                logger.info(
                    "Stored similarity data for workflow=%s: %d agents, highest=%.2f",
                    workflow_id,
                    len(similar_agents),
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
    workflow_id = body.get("workflow_id")

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

            # Build context-enriched evaluation prompt
            eval_prompt_parts = [
                "Evaluate the quality of this AGENTS.md file.\n",
                "Score across 5 dimensions (clarity, completeness, specificity, ",
                "consistency, differentiation). For each: score 0-10, cite evidence, ",
                "list issues.\n\n",
                "Calculate overall_score using weights: ",
                "clarity*0.25 + completeness*0.25 + specificity*0.20 ",
                "+ consistency*0.15 + differentiation*0.15\n\n",
                "Assign grade: A (9-10), B (7-8.9), C (5-6.9), D (3-4.9), F (0-2.9)\n\n",
                "For each issue: classify severity (critical/major/minor), ",
                "describe problem, identify location, suggest fix.\n\n",
            ]

            # Enrich with similarity context if available
            if workflow_id:
                similar_agents = session_mgr.get_workflow_metadata(
                    workflow_id, "similar_agents", []
                )
                highest_sim = session_mgr.get_workflow_metadata(
                    workflow_id, "highest_similarity", 0.0
                )

                if similar_agents:
                    eval_prompt_parts.append(
                        f"\n**CONTEXT: Catalogue Analysis**\n"
                        f"This agent has {len(similar_agents)} similar agents in the catalogue "
                        f"(highest similarity: {highest_sim:.1%}):\n\n"
                    )
                    for sa in similar_agents[:3]:  # Top 3
                        eval_prompt_parts.append(
                            f"- **{sa['name']}** ({sa['similarity_score']:.1%} similar)\n"
                            f"  Shared capabilities: {', '.join(sa['shared_capabilities'][:3])}\n"
                        )
                    eval_prompt_parts.append(
                        "\nWhen scoring DIFFERENTIATION dimension, consider this overlap. "
                        "Strong differentiation requires clear boundaries vs these "
                        "existing agents.\n\n"
                    )

            eval_prompt_parts.append(
                "Return JSON with: dimensions (list), overall_score, grade, "
                "issues (list), strengths (list), summary.\n\n"
                f"<content>\n{content_str}\n</content>"
            )

            eval_prompt = "".join(eval_prompt_parts)

            if workflow_id:
                eval_response = await session_mgr.run_with_sticky_session(
                    workflow_id, "evaluator", eval_prompt, queue
                )
            else:
                eval_response = await session_mgr.run_one_shot_streaming(
                    "evaluator", eval_prompt, queue
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
    workflow_id = body.get("workflow_id")  # Optional for sticky sessions

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

            # Build improvement prompt with catalogue context
            improve_prompt_parts = [
                "Improve this AGENTS.md definition based on the quality evaluation below.\n\n",
                f"<original_content>\n{content_str}\n</original_content>\n\n",
                "<evaluation_summary>\n",
                f"Overall score: {evaluation.get('overall_score', 'N/A')}/10 ",
                f"(Grade: {evaluation.get('grade', 'N/A')})\n\n",
                f"Issues to address:\n{issues_text}\n",
                "</evaluation_summary>\n\n",
            ]

            # Enrich with stored similarity data (avoid redundant search_similar calls)
            if workflow_id:
                similar_agents = session_mgr.get_workflow_metadata(
                    workflow_id, "similar_agents", []
                )
                if similar_agents:
                    improve_prompt_parts.append(
                        f"<catalogue_context>\n"
                        f"Analysis found {len(similar_agents)} similar agents. "
                        f"Differentiate from these:\n\n"
                    )
                    for sa in similar_agents[:3]:
                        improve_prompt_parts.append(
                            f"- **{sa['name']}** ({sa['similarity_score']:.1%} similar)\n"
                            f"  Shared: {', '.join(sa['shared_capabilities'][:3])}\n"
                            f"  Your unique: {', '.join(sa['unique_capabilities'][:3])}\n"
                        )
                    improve_prompt_parts.append(
                        "\nDO NOT use search_similar - this data is already provided above.\n"
                        "</catalogue_context>\n\n"
                    )
                else:
                    improve_prompt_parts.append(
                        "You have access to search_similar and get_agent_content "
                        "tools if needed.\n\n"
                    )
            else:
                improve_prompt_parts.append(
                    "You have access to search_similar and get_agent_content tools.\n\n"
                )

            improve_prompt_parts.extend(
                [
                    "Generate an improved version that:\n",
                    "1. Fixes all identified quality issues\n",
                    "2. Differentiates from similar agents (using context above)\n",
                    "3. Carves out a unique niche\n\n",
                    f"Original token count: {original_token_count}. Aim for under 1500 tokens.\n\n",
                    "Output ONLY the improved raw markdown. No preamble, no code fences.",
                ]
            )

            improve_prompt_text = "".join(improve_prompt_parts)

            # Use sticky session if workflow_id provided
            if workflow_id:
                improved_raw = await session_mgr.run_with_sticky_session(
                    workflow_id, "improver", improve_prompt_text, queue
                )
            else:
                improved_raw = await session_mgr.run_one_shot_streaming(
                    "improver", improve_prompt_text, queue
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


@router.post("/api/stream/refine")
async def stream_refine(request: Request) -> StreamingResponse:
    """SSE streaming version of refine - shows differentiator agent reasoning.

    Emits kernel events (thinking, tool calls) as they happen during
    strategic differentiation to reduce overlap with existing agents.
    """
    from uuid import UUID

    body = await request.json()
    content_str = body.get("content", "")
    overlapping = body.get("overlapping_agents", [])
    workflow_id = body.get("workflow_id")

    if not content_str:
        raise HTTPException(status_code=400, detail="content is required")

    session_mgr = request.app.state.session_mgr
    db_repo = request.app.state.db_repo
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        await queue.put({"event": event, "data": data})

    async def run() -> None:
        try:
            # Phase: refining
            await _emit(
                "phase",
                {
                    "phase": "refining",
                    "message": "Differentiator agent applying strategic frameworks...",
                    "agent_name": "differentiator",
                },
            )

            # Get overlap data from workflow metadata OR frontend
            if workflow_id:
                # Prefer stored metadata (has similarity scores and overlap analysis)
                stored_similar = session_mgr.get_workflow_metadata(
                    workflow_id, "similar_agents", []
                )
                if stored_similar:
                    logger.info(
                        "Using stored similarity data: %d agents (highest: %.2f)",
                        len(stored_similar),
                        session_mgr.get_workflow_metadata(workflow_id, "highest_similarity", 0.0),
                    )
                    # Use stored IDs for fetching full content
                    agent_ids = [s["id"] for s in stored_similar[:3]]
                else:
                    # Fallback to frontend overlapping_agents
                    agent_ids = [agent.get("id") for agent in overlapping if agent.get("id")]
            else:
                agent_ids = [agent.get("id") for agent in overlapping if agent.get("id")]

            # Fetch full agent content for strategic analysis
            full_agents = []
            for agent_id in agent_ids[:3]:  # Limit to top 3
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
                            "full_content": latest_content[:2000],
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
                    f"{i}. **{agent['name']}\n"
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

            # Run differentiator with streaming (sticky if workflow_id provided)
            if workflow_id:
                refined_raw = await session_mgr.run_with_sticky_session(
                    workflow_id, "differentiator", refine_prompt, queue
                )
            else:
                refined_raw = await session_mgr.run_one_shot_streaming(
                    "differentiator", refine_prompt, queue
                )

            if not refined_raw or len(refined_raw.strip()) < 100:
                raise HTTPException(
                    status_code=500, detail="Differentiator returned insufficient output"
                )

            refined = strip_preamble(refined_raw)
            changes = compute_diff_sections(content_str, refined)
            token_metrics = to_token_metrics(refined)

            # Emit final result
            await _emit(
                "result",
                {
                    "refined_content": refined,
                    "original_content": content_str,
                    "changes": changes,
                    "token_metrics": token_metrics.model_dump(),
                },
            )

        except Exception as e:
            logger.exception("SSE refine failed")
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


@router.delete("/api/session/{workflow_id}")
async def cleanup_workflow_session(workflow_id: str, request: Request):
    """Cleanup sticky workflow session.

    Called when upload completes successfully or user cancels/navigates away.
    Disposes of the Amplifier session and frees resources.
    """
    session_mgr = request.app.state.session_mgr

    await session_mgr.cleanup_workflow(workflow_id)

    logger.info("Cleaned up workflow session: %s", workflow_id)
    return {"status": "ok", "workflow_id": workflow_id}
