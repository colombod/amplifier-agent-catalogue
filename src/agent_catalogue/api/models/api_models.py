"""API request/response models for Agent Catalogue.

This module contains all Pydantic models used in FastAPI endpoints,
extracted from routes.py for better organization and reusability.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_catalogue.models.agent import AgentSummary, SimilarAgent, SimilarAgentWithComparison
from agent_catalogue.models.extraction import ExtractedMetadata

# ---------------------------------------------------------------------------
# Token Metrics
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


# ---------------------------------------------------------------------------
# Upload/Analysis Response Models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Quality Evaluation Models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Refinement Models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Recipe Execution Models
# ---------------------------------------------------------------------------


class RecipeStartRequest(BaseModel):
    """Request to start a recipe execution."""

    recipe_path: str = Field(..., description="Path to recipe YAML file")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Context variables for recipe"
    )


class RecipeStartResponse(BaseModel):
    """Response from recipe start endpoint."""

    session_id: str = Field(..., description="Recipe session identifier")
    status: str = Field(..., description="Initial status (usually 'running')")


class RecipeStatusResponse(BaseModel):
    """Response from recipe status endpoint."""

    session_id: str
    status: str = Field(..., description="running | paused_for_approval | completed | failed")
    recipe_name: str | None = None
    current_stage: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    approval_needed: bool = False
    pending_approval: dict[str, Any] | None = None


class RecipeSessionsResponse(BaseModel):
    """Response from list recipe sessions endpoint."""

    sessions: list[dict[str, Any]]
    count: int


class RecipeApprovalResponse(BaseModel):
    """Response from recipe approval endpoint."""

    status: str = Field(..., description="Status after approval (usually 'resumed')")
    session_id: str


class RecipeDenyRequest(BaseModel):
    """Request to deny a recipe stage."""

    reason: str | None = Field(None, description="Optional reason for denial")


class RecipeDenyResponse(BaseModel):
    """Response from recipe deny endpoint."""

    status: str = Field(..., description="Status after denial (usually 'denied')")
    session_id: str
