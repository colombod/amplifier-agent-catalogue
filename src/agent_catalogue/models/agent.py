"""Core agent domain models."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentVersion(BaseModel):
    """A specific version of an agent."""

    id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    version_number: int
    raw_content: str
    content_hash: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    change_summary: str | None = None
    token_count: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class Agent(BaseModel):
    """An agent in the catalogue."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    description: str = ""
    current_version_id: UUID | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships (populated when loaded)
    current_version: AgentVersion | None = None
    versions: list[AgentVersion] = Field(default_factory=list)

    class Config:
        from_attributes = True


class AgentSummary(BaseModel):
    """Lightweight agent summary for listings."""

    id: UUID
    name: str
    slug: str
    description: str
    version_count: int
    current_version: int
    domains: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    token_count: int | None = None
    updated_at: datetime


class SimilarAgent(BaseModel):
    """An agent found during similarity search."""

    agent: AgentSummary
    similarity_score: float
    match_type: str  # "exact", "semantic", "facet"
    matched_on: list[str] = Field(default_factory=list)  # What facets matched


class SearchResult(BaseModel):
    """A search result with relevance scoring."""

    agent: AgentSummary
    score: float
    semantic_score: float
    facet_matches: list[str] = Field(default_factory=list)
    explanation: str = ""
    capabilities_matched: list[str] = Field(default_factory=list)


class VersionDiff(BaseModel):
    """Diff between two versions of an agent."""

    from_version: int
    to_version: int
    content_diff: str
    capabilities_added: list[str] = Field(default_factory=list)
    capabilities_removed: list[str] = Field(default_factory=list)
    tools_added: list[str] = Field(default_factory=list)
    tools_removed: list[str] = Field(default_factory=list)
    domains_added: list[str] = Field(default_factory=list)
    domains_removed: list[str] = Field(default_factory=list)
    embedding_distance: float = 0.0
    change_summary: str = ""


class TraitComparison(BaseModel):
    """Comparison of a specific trait between two agents."""

    trait_name: str  # e.g., "capabilities", "domains", "tools"
    shared: list[str] = Field(default_factory=list)  # In both
    only_in_new: list[str] = Field(default_factory=list)  # Only in uploaded
    only_in_existing: list[str] = Field(default_factory=list)  # Only in existing
    overlap_ratio: float = 0.0  # |shared| / |union|


class AgentComparison(BaseModel):
    """Detailed comparison between uploaded agent and an existing one."""

    existing_agent: AgentSummary
    similarity_score: float  # Overall semantic similarity

    # Trait comparisons
    capabilities: TraitComparison
    domains: TraitComparison
    tools: TraitComparison
    behaviors: TraitComparison
    triggers: TraitComparison

    # High-level summary
    shared_purpose: bool = False  # Do they solve the same problem?
    purpose_comparison: str = ""  # LLM-generated explanation
    recommendation: str = ""  # "merge", "keep_separate", "replace"
    recommendation_reason: str = ""

    @property
    def has_significant_overlap(self) -> bool:
        """Check if there's significant trait overlap (>50% in any category)."""
        return any(
            t.overlap_ratio > 0.5
            for t in [
                self.capabilities,
                self.domains,
                self.tools,
            ]
        )

    @property
    def is_likely_duplicate(self) -> bool:
        """Check if this is likely a duplicate (>80% similarity + overlap)."""
        return self.similarity_score > 0.8 and self.has_significant_overlap


class SimilarAgentWithComparison(BaseModel):
    """Similar agent with detailed trait comparison."""

    agent: AgentSummary
    similarity_score: float
    comparison: AgentComparison
    match_type: str = "semantic"  # "exact", "semantic", "partial"
