"""Models for AGENTS.md parsing and LLM extraction."""

from typing import Literal

from pydantic import BaseModel, Field


class ParsedSection(BaseModel):
    """A section extracted from markdown."""

    header: str
    level: int  # 1 = #, 2 = ##, etc.
    content: str
    start_line: int
    end_line: int


class ParsedDocument(BaseModel):
    """Result of parsing an AGENTS.md file."""

    title: str | None = None
    sections: list[ParsedSection] = Field(default_factory=list)
    raw_content: str = ""
    content_hash: str = ""

    def get_section(self, *headers: str) -> ParsedSection | None:
        """Get a section by header name (case-insensitive, tries multiple)."""
        for section in self.sections:
            if section.header.lower() in [h.lower() for h in headers]:
                return section
        return None

    def get_sections_by_level(self, level: int) -> list[ParsedSection]:
        """Get all sections at a specific header level."""
        return [s for s in self.sections if s.level == level]


class ExtractedMetadata(BaseModel):
    """Metadata extracted from AGENTS.md using LLM."""

    # Identity
    name: str = Field(description="Name of the agent")
    slug: str = Field(description="URL-safe identifier")

    # Core content
    description: str = Field(description="Brief description of what this agent does")
    purpose: str = Field(description="Why this agent exists, what problem it solves")

    # Capabilities
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of things this agent can do",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Domains/areas where this agent is useful (e.g., 'code review', 'security')",
    )

    # Technical
    tools: list[str] = Field(
        default_factory=list,
        description="Tools this agent uses or requires",
    )
    behaviors: list[str] = Field(
        default_factory=list,
        description="Behavioral patterns or modes",
    )
    triggers: list[str] = Field(
        default_factory=list,
        description="When/how this agent should be invoked",
    )

    # Classification
    complexity: Literal["simple", "moderate", "complex"] = Field(
        default="moderate",
        description="How complex is this agent?",
    )
    autonomy: Literal["autonomous", "guided", "hybrid"] = Field(
        default="hybrid",
        description="Level of autonomy (autonomous, guided, or hybrid)",
    )

    # Generated
    keywords: list[str] = Field(
        default_factory=list,
        description="Search keywords for discovery",
    )
    summary: str = Field(
        default="",
        description="One-paragraph summary for search results",
    )


EXTRACTION_SYSTEM_PROMPT = """\
You are an expert at analyzing AGENTS.md files and extracting structured metadata.

AGENTS.md files describe AI agents - their purpose, capabilities, tools, and when to use them.

Extract the following information:
- name: The agent's name
- slug: A URL-safe version of the name (lowercase, hyphens)
- description: A brief one-sentence description
- purpose: Why this agent exists, what problem it solves
- capabilities: List of specific things this agent can do
- domains: Areas where this agent is useful (e.g., "debugging", "code review", "security")
- tools: Tools the agent uses (e.g., "bash", "git", "LSP")
- behaviors: How the agent behaves or operates
- triggers: When/how this agent should be invoked
- complexity: simple, moderate, or complex
- autonomy: autonomous, guided, or hybrid
- keywords: Search terms for finding this agent
- summary: A one-paragraph summary for search results

Be thorough but concise. Extract real information from the document, don't invent capabilities.
"""

EXTRACTION_USER_TEMPLATE = """\
Analyze this AGENTS.md file and extract structured metadata.

{content}

Return a JSON object with the extracted metadata.
"""
