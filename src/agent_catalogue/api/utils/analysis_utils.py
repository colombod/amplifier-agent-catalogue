"""Shared utilities for analysis operations."""

import re
from typing import Any

from agent_catalogue.models.extraction import ExtractedMetadata


def generate_slug(name: str) -> str:
    """Generate URL-safe slug from name.

    Args:
        name: Agent name to convert to slug

    Returns:
        URL-safe slug string
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-") or "unknown"


def build_metadata(
    data: dict[str, Any],
    document: Any,
) -> ExtractedMetadata:
    """Build ExtractedMetadata from LLM-extracted dict with fallbacks.

    Args:
        data: Dict parsed from LLM JSON output
        document: ParsedDocument for fallback values (title, etc.)

    Returns:
        Validated ExtractedMetadata instance
    """
    name = data.get("name") or getattr(document, "title", None) or "Unknown Agent"
    slug = generate_slug(data.get("slug") or name)

    def _ensure_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            return [value] if value else []
        return []

    complexity_val = data.get("complexity", "moderate")
    if complexity_val not in {"simple", "moderate", "complex"}:
        complexity_val = "moderate"

    autonomy_val = data.get("autonomy", "hybrid")
    if autonomy_val not in {"autonomous", "guided", "hybrid"}:
        autonomy_val = "hybrid"

    return ExtractedMetadata(
        name=name,
        slug=slug,
        description=data.get("description", ""),
        purpose=data.get("purpose", ""),
        capabilities=_ensure_list(data.get("capabilities", [])),
        domains=_ensure_list(data.get("domains", [])),
        tools=_ensure_list(data.get("tools", [])),
        behaviors=_ensure_list(data.get("behaviors", [])),
        triggers=_ensure_list(data.get("triggers", [])),
        complexity=complexity_val,
        autonomy=autonomy_val,
        keywords=_ensure_list(data.get("keywords", [])),
        summary=data.get("summary", ""),
    )
