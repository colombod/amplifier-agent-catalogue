"""Recipe execution endpoints for multi-stage workflows with approval gates.

Integrates Amplifier recipes tool for executing differentiate-agent.yaml and other
multi-step workflows. Handles approval gate mechanics, status polling, and event streaming.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ===================================================================
# Request/Response Models
# ===================================================================


class RecipeStartRequest(BaseModel):
    """Request to start recipe execution."""

    recipe_path: str
    context: dict[str, Any]


class RecipeApprovalRequest(BaseModel):
    """Request to approve/deny a stage."""

    session_id: str
    stage_name: str
    action: str  # "approve" or "deny"
    reason: str | None = None


class RecipeStatusResponse(BaseModel):
    """Recipe execution status."""

    session_id: str
    recipe_name: str
    status: str  # "running", "paused_for_approval", "completed", "cancelled"
    current_stage: str | None = None
    pending_approval: dict[str, Any] | None = None
    completed_steps: list[str] = []
    summary: dict[str, Any] | None = None


# ===================================================================
# Recipe Execution Endpoints
# ===================================================================


@router.post("/api/recipe/start")
async def start_recipe(request: Request, body: RecipeStartRequest) -> dict[str, Any]:
    """Start recipe execution.

    Returns immediately with session_id. Recipe runs in background.
    Client should poll /api/recipe/status or subscribe to /api/recipe/events.
    """
    session_mgr = request.app.state.session_mgr

    # Create temp session to access recipes tool
    temp_session = await session_mgr._create_session()
    try:
        # CRITICAL: Register spawn capability on THIS session's coordinator
        # The recipes tool will check this coordinator for spawn capability
        temp_session.coordinator.register_capability(
            "session.spawn", session_mgr._create_spawn_callback_for_recipes()
        )
        logger.info("Registered session.spawn capability on recipe execution session")

        recipes_tool = temp_session.coordinator.mount_points.get("tools", {}).get("recipes")
        if not recipes_tool:
            raise HTTPException(
                status_code=500,
                detail="Recipes tool not mounted - check SessionManager config",
            )

        logger.info("Starting recipe: %s", body.recipe_path)
        logger.info("Context variables: %s", list(body.context.keys()))

        # Execute recipe - returns immediately if paused at approval
        result = await recipes_tool.execute(
            {
                "operation": "execute",
                "recipe_path": body.recipe_path,
                "context": body.context,
            }
        )

        if not result.success:
            logger.error("Recipe execution failed: %s", result.error)
            raise HTTPException(status_code=500, detail=str(result.error))

        output = result.output

        logger.info("Recipe execution result: %s", output.get("status"))

        # Check if paused at approval gate
        if output.get("status") == "paused_for_approval":
            return {
                "status": "paused",
                "session_id": output["session_id"],
                "stage_name": output["stage_name"],
                "approval_prompt": output.get("approval_prompt", ""),
                "message": f"Recipe paused at stage '{output['stage_name']}' - awaiting approval",
            }

        # Completed without approval gates
        return {
            "status": "completed",
            "session_id": output["session_id"],
            "summary": output.get("summary", {}),
            "message": "Recipe completed successfully",
        }

    finally:
        await temp_session.cleanup()


@router.post("/api/recipe/approve")
async def approve_stage(request: Request, body: RecipeApprovalRequest) -> dict[str, Any]:
    """Approve or deny a stage and resume recipe execution."""
    session_mgr = request.app.state.session_mgr

    temp_session = await session_mgr._create_session()
    try:
        recipes_tool = temp_session.coordinator.mount_points.get("tools", {}).get("recipes")
        if not recipes_tool:
            raise HTTPException(status_code=500, detail="Recipes tool not mounted")

        logger.info(
            "Processing approval: session=%s stage=%s action=%s",
            body.session_id,
            body.stage_name,
            body.action,
        )

        # Submit approval or denial
        if body.action == "approve":
            approval_result = await recipes_tool.execute(
                {
                    "operation": "approve",
                    "session_id": body.session_id,
                    "stage_name": body.stage_name,
                }
            )
        elif body.action == "deny":
            approval_result = await recipes_tool.execute(
                {
                    "operation": "deny",
                    "session_id": body.session_id,
                    "stage_name": body.stage_name,
                    "reason": body.reason or "User declined",
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Action must be 'approve' or 'deny'")

        if not approval_result.success:
            raise HTTPException(status_code=500, detail=str(approval_result.error))

        logger.info("Approval processed, resuming recipe...")

        # Resume execution (may pause at another gate)
        resume_result = await recipes_tool.execute(
            {"operation": "resume", "session_id": body.session_id}
        )

        if not resume_result.success:
            raise HTTPException(status_code=500, detail=str(resume_result.error))

        output = resume_result.output

        # Check if paused again at another approval gate
        if output.get("status") == "paused_for_approval":
            return {
                "status": "paused",
                "stage_name": output["stage_name"],
                "approval_prompt": output.get("approval_prompt", ""),
                "message": (
                    f"Recipe paused at next stage '{output['stage_name']}' - awaiting approval"
                ),
            }

        # Completed
        return {
            "status": "completed",
            "summary": output.get("summary", {}),
            "message": "Recipe completed successfully",
        }

    finally:
        await temp_session.cleanup()


@router.get("/api/recipe/status/{session_id}")
async def get_recipe_status(request: Request, session_id: str) -> RecipeStatusResponse:
    """Get current status of a recipe session."""
    session_mgr = request.app.state.session_mgr

    temp_session = await session_mgr._create_session()
    try:
        recipes_tool = temp_session.coordinator.mount_points.get("tools", {}).get("recipes")
        if not recipes_tool:
            raise HTTPException(status_code=500, detail="Recipes tool not mounted")

        # Get all sessions
        list_result = await recipes_tool.execute({"operation": "list"})

        if not list_result.success:
            raise HTTPException(status_code=500, detail=str(list_result.error))

        sessions = list_result.output.get("sessions", [])
        session = next((s for s in sessions if s["session_id"] == session_id), None)

        if not session:
            raise HTTPException(status_code=404, detail="Recipe session not found")

        # Check for pending approvals
        approvals_result = await recipes_tool.execute({"operation": "approvals"})

        pending_approvals = approvals_result.output.get("pending_approvals", [])
        pending = next((a for a in pending_approvals if a["session_id"] == session_id), None)

        return RecipeStatusResponse(
            session_id=session_id,
            recipe_name=session.get("recipe_name", "unknown"),
            status=session.get("status", "unknown"),
            current_stage=session.get("current_stage"),
            pending_approval=pending,
            completed_steps=session.get("completed_steps", []),
            summary=session.get("summary"),
        )

    finally:
        await temp_session.cleanup()


@router.get("/api/recipe/sessions")
async def list_recipe_sessions(request: Request) -> dict[str, Any]:
    """List all recipe sessions."""
    session_mgr = request.app.state.session_mgr

    temp_session = await session_mgr._create_session()
    try:
        recipes_tool = temp_session.coordinator.mount_points.get("tools", {}).get("recipes")
        if not recipes_tool:
            raise HTTPException(status_code=500, detail="Recipes tool not mounted")

        result = await recipes_tool.execute({"operation": "list"})

        if not result.success:
            raise HTTPException(status_code=500, detail=str(result.error))

        return result.output

    finally:
        await temp_session.cleanup()


@router.get("/api/recipe/approvals")
async def list_pending_approvals(request: Request) -> dict[str, Any]:
    """List all pending approvals across all recipe sessions."""
    session_mgr = request.app.state.session_mgr

    temp_session = await session_mgr._create_session()
    try:
        recipes_tool = temp_session.coordinator.mount_points.get("tools", {}).get("recipes")
        if not recipes_tool:
            raise HTTPException(status_code=500, detail="Recipes tool not mounted")

        result = await recipes_tool.execute({"operation": "approvals"})

        if not result.success:
            raise HTTPException(status_code=500, detail=str(result.error))

        return result.output

    finally:
        await temp_session.cleanup()


@router.post("/api/recipe/cancel/{session_id}")
async def cancel_recipe(
    request: Request, session_id: str, immediate: bool = False
) -> dict[str, Any]:
    """Cancel a running recipe session."""
    session_mgr = request.app.state.session_mgr

    temp_session = await session_mgr._create_session()
    try:
        recipes_tool = temp_session.coordinator.mount_points.get("tools", {}).get("recipes")
        if not recipes_tool:
            raise HTTPException(status_code=500, detail="Recipes tool not mounted")

        result = await recipes_tool.execute(
            {"operation": "cancel", "session_id": session_id, "immediate": immediate}
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=str(result.error))

        cancel_msg = "immediately cancelled" if immediate else "cancelled gracefully"
        return {
            "status": "cancelled",
            "session_id": session_id,
            "message": f"Recipe {cancel_msg}",
        }

    finally:
        await temp_session.cleanup()
