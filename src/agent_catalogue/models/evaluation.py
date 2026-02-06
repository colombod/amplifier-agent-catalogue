"""Models for agent quality evaluation and improvement."""

from typing import Literal

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """Score for a single quality dimension."""

    dimension: Literal["clarity", "completeness", "specificity", "consistency", "differentiation"]
    score: float = Field(ge=0.0, le=10.0, description="Score from 0-10")
    evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence from the content",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific problems found in this dimension",
    )


class QualityIssue(BaseModel):
    """A specific quality issue with improvement suggestion."""

    dimension: str
    severity: Literal["critical", "major", "minor"]
    description: str
    location: str = ""  # Where in the document
    suggestion: str = ""  # Concrete fix


class QualityEvaluation(BaseModel):
    """Complete quality evaluation result."""

    dimensions: list[DimensionScore] = Field(default_factory=list)
    overall_score: float = Field(ge=0.0, le=10.0, default=5.0)
    grade: Literal["A", "B", "C", "D", "F"] = "C"
    issues: list[QualityIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    summary: str = ""

    @property
    def has_critical_issues(self) -> bool:
        """Check if any critical issues were found."""
        return any(i.severity == "critical" for i in self.issues)

    @property
    def issue_count_by_severity(self) -> dict[str, int]:
        """Count issues by severity."""
        counts: dict[str, int] = {"critical": 0, "major": 0, "minor": 0}
        for issue in self.issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return counts


class ImprovementResult(BaseModel):
    """Result of auto-improvement."""

    improved_content: str
    changes_made: list[str] = Field(default_factory=list)
    issues_addressed: int = 0
