"""Response formatting utilities for API endpoints.

This module provides utilities for formatting evaluation responses,
grade labels, and token metrics.
"""

from __future__ import annotations

from typing import Any

from agent_catalogue.api.models.api_models import TokenMetrics
from agent_catalogue.services.token_metrics import analyze_tokens


def grade_label(grade: str) -> str:
    """Map letter grade to human-readable label."""
    labels = {
        "A": "Excellent",
        "B": "Good",
        "C": "Adequate",
        "D": "Needs Work",
        "F": "Poor",
    }
    return labels.get(grade, "Unknown")


def estimate_improved_score(evaluation: dict[str, Any]) -> tuple[float, str]:
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


def to_token_metrics(text: str) -> TokenMetrics:
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
