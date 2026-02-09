"""Agent comparison routes.

Provides endpoints for comparing new agent definitions against existing agents
in the catalogue to identify behavioral overlaps and differences.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from agent_catalogue.api.utils.json_extractor import extract_json
from agent_catalogue.services.parser import ParserService

logger = logging.getLogger(__name__)

router = APIRouter()
_parser = ParserService()


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

    compare_response = await session_mgr.run_one_shot("comparator", compare_prompt)
    comparison = extract_json(compare_response) or {}

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

    narrative = await session_mgr.run_one_shot("narrator", narrate_prompt)

    return {
        "comparison": comparison,
        "narrative": narrative,
        "new_agent": new_name,
        "existing_agent": existing_agent.name,
    }


@router.post("/api/stream/compare/{agent_id}")
async def stream_compare_with_agent(
    request: Request,
    agent_id: UUID,
) -> StreamingResponse:
    """SSE streaming version of compare - shows real-time agent reasoning.

    Two phases:
    1. Comparator agent analyzing behavioral differences (LLM)
    2. Narrator agent generating human-readable explanation (LLM)
    """
    body = await request.json()
    new_content = body.get("content", "")
    if not new_content:
        raise HTTPException(status_code=400, detail="content is required")

    db_repo = request.app.state.db_repo
    session_mgr = request.app.state.session_mgr
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _emit(event: str, data: dict[str, Any]) -> None:
        await queue.put({"event": event, "data": data})

    async def run() -> None:
        try:
            # Get existing agent
            existing_agent = db_repo.get_agent(agent_id)
            if not existing_agent:
                await _emit("error", {"message": "Agent not found"})
                return

            if not existing_agent.current_version_id:
                await _emit("error", {"message": "Agent has no versions"})
                return

            existing_version = db_repo.get_version(existing_agent.current_version_id)
            if not existing_version:
                await _emit("error", {"message": "Agent version not found"})
                return

            new_document = _parser.parse(new_content)
            new_name = new_document.title or "Uploaded Agent"

            # Phase 1: Deep comparison
            await _emit(
                "phase",
                {
                    "phase": "comparing",
                    "message": "Comparator agent analyzing behavioral differences...",
                    "agent_name": "comparator",
                },
            )

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

            compare_response = await session_mgr.run_one_shot_streaming(
                "comparator",
                compare_prompt,
                queue,
            )

            comparison = extract_json(compare_response) or {}

            # Phase 2: Generate narrative
            await _emit(
                "phase",
                {
                    "phase": "narrating",
                    "message": "Narrator agent generating explanation...",
                    "agent_name": "narrator",
                },
            )

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

            narrative = await session_mgr.run_one_shot_streaming(
                "narrator",
                narrate_prompt,
                queue,
            )

            # Emit final result
            await _emit(
                "result",
                {
                    "comparison": comparison,
                    "narrative": narrative,
                    "new_agent": new_name,
                    "existing_agent": existing_agent.name,
                },
            )

        except Exception as e:
            logger.exception("SSE compare failed")
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
