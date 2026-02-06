"""Token metrics analysis for AGENTS.md files.

Measures token count, efficiency, and provides budget guidance.
These files are loaded into LLM context windows at every turn,
so token efficiency directly impacts agent performance and cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

# cl100k_base is the encoding used by GPT-4o / GPT-4 / text-embedding-3-*
_ENCODING = tiktoken.get_encoding("cl100k_base")

# Budget thresholds (tokens)
BUDGET_LEAN = 500  # Very efficient, single-purpose agents
BUDGET_MODERATE = 1500  # Well-structured agents with clear scope
BUDGET_HEAVY = 3000  # Complex agents — consider splitting
BUDGET_EXCESSIVE = 5000  # Almost certainly too large


@dataclass
class SectionTokens:
    """Token breakdown for a single markdown section."""

    heading: str
    tokens: int
    lines: int
    pct_of_total: float


@dataclass
class TokenAnalysis:
    """Complete token analysis of an AGENTS.md file."""

    total_tokens: int
    total_lines: int
    total_chars: int
    tokens_per_line: float
    sections: list[SectionTokens]
    budget_category: str  # lean / moderate / heavy / excessive
    budget_label: str  # human-readable label
    recommendation: str  # actionable guidance


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return len(_ENCODING.encode(text))


def analyze_tokens(content: str) -> TokenAnalysis:
    """Analyze token usage of an AGENTS.md file.

    Returns a full breakdown by section with budget guidance.
    """
    total_tokens = count_tokens(content)
    lines = content.split("\n")
    total_lines = len(lines)
    total_chars = len(content)

    # Split into sections by markdown headings
    sections: list[SectionTokens] = []
    current_heading = "(preamble)"
    current_lines: list[str] = []

    for line in lines:
        if re.match(r"^#{1,6}\s", line):
            # Flush previous section
            if current_lines:
                section_text = "\n".join(current_lines)
                section_tokens = count_tokens(section_text)
                sections.append(
                    SectionTokens(
                        heading=current_heading,
                        tokens=section_tokens,
                        lines=len(current_lines),
                        pct_of_total=(
                            round(section_tokens / total_tokens * 100, 1) if total_tokens > 0 else 0
                        ),
                    )
                )
            current_heading = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush last section
    if current_lines:
        section_text = "\n".join(current_lines)
        section_tokens = count_tokens(section_text)
        sections.append(
            SectionTokens(
                heading=current_heading,
                tokens=section_tokens,
                lines=len(current_lines),
                pct_of_total=(
                    round(section_tokens / total_tokens * 100, 1) if total_tokens > 0 else 0
                ),
            )
        )

    # Budget classification
    if total_tokens <= BUDGET_LEAN:
        category, label = "lean", "Lean"
        recommendation = (
            "Compact and efficient. Loads quickly into context with minimal token overhead."
        )
    elif total_tokens <= BUDGET_MODERATE:
        category, label = "moderate", "Moderate"
        recommendation = "Well-sized for most agents. Good balance of detail and token efficiency."
    elif total_tokens <= BUDGET_HEAVY:
        category, label = "heavy", "Heavy"
        recommendation = (
            "Large context footprint. Review sections for "
            "content that could be moved to external docs "
            "or trimmed without losing actionable guidance."
        )
    else:
        category, label = "excessive", "Excessive"
        recommendation = (
            "This file consumes significant context window on every "
            "turn. Consider splitting into a concise AGENTS.md with "
            "references to separate docs for detailed procedures."
        )

    tokens_per_line = round(total_tokens / total_lines, 1) if total_lines > 0 else 0

    return TokenAnalysis(
        total_tokens=total_tokens,
        total_lines=total_lines,
        total_chars=total_chars,
        tokens_per_line=tokens_per_line,
        sections=sections,
        budget_category=category,
        budget_label=label,
        recommendation=recommendation,
    )
