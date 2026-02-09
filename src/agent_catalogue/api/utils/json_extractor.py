"""JSON extraction utilities for parsing LLM responses.

This module provides utilities to extract JSON from LLM prose responses,
which may include preambles, code fences, or markdown formatting.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM response text.

    Tries, in order:
    1. JSON inside ```json ... ``` fences
    2. JSON inside ``` ... ``` fences
    3. First balanced { ... } substring
    4. Direct parse of the whole string

    Returns None on failure.
    """
    if not text:
        return None

    stripped = text.strip()

    # 1. ```json code fence
    if "```json" in stripped:
        start = stripped.find("```json") + 7
        end = stripped.find("```", start)
        if end > start:
            candidate = stripped[start:end].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 2. ``` code fence (any language)
    if "```" in stripped:
        start = stripped.find("```") + 3
        # Skip optional language tag on same line
        newline = stripped.find("\n", start)
        if newline != -1:
            start = newline + 1
        end = stripped.find("```", start)
        if end > start:
            candidate = stripped[start:end].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 3. Balanced brace matching
    brace_start = stripped.find("{")
    if brace_start != -1:
        depth = 0
        for i in range(brace_start, len(stripped)):
            if stripped[i] == "{":
                depth += 1
            elif stripped[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[brace_start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    # 4. Whole string
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        logger.warning("Direct parse failed: %s", str(e))

    # All methods failed - log what we received
    logger.error(
        "Failed to extract JSON from LLM response (%d chars). First 300 chars: %s",
        len(text),
        text[:300],
    )
    return None


def strip_preamble(text: str) -> str:
    """Strip LLM thinking/commentary before the actual markdown content.

    The model sometimes prepends reasoning or wraps output in code fences.
    This finds the first markdown heading and returns everything from there.
    """
    stripped = text.strip()

    # Strip wrapping code fences (```markdown ... ```)
    if stripped.startswith("```"):
        first_nl = stripped.index("\n") if "\n" in stripped else len(stripped)
        stripped = stripped[first_nl + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()

    # Find the first markdown heading – that is where real content starts
    lines = stripped.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return "\n".join(lines[i:]).strip()

    return stripped.strip()
