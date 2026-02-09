"""Agent search routes.

Provides endpoints for searching the agent catalogue using vector similarity,
metadata filters, and HyDE (Hypothetical Document Embedding) for semantic search.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from agent_catalogue.api.utils.json_extractor import extract_json
from agent_catalogue.models.agent import SearchResult, SimilarAgent

logger = logging.getLogger(__name__)

router = APIRouter()


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

    hypothetical_doc = await session_mgr.run_one_shot("discovery", hyde_prompt)

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

    explain_response = await session_mgr.run_one_shot("relevance", explain_prompt)
    explanations_raw = extract_json(explain_response)

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
                    "message": "Discovery agent generating hypothetical agent description...",
                    "agent_name": "discovery",
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
                "discovery", hyde_prompt, queue
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
                    "message": "Relevance agent explaining relevance of results...",
                    "agent_name": "relevance",
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
                "relevance", explain_prompt, queue
            )
            explanations_raw = extract_json(explain_response)

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
