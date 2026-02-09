"""Diff computation utilities for comparing markdown documents.

This module provides utilities for computing section-level diffs
between original and improved markdown content.
"""

from __future__ import annotations

import re
from typing import Any


def compute_diff_sections(original: str, improved: str) -> list[dict[str, Any]]:
    """Compute section-level diff between original and improved markdown.

    Splits both documents by markdown headings, then compares each section
    to determine if it was added, removed, modified, or unchanged.

    Args:
        original: Original markdown content
        improved: Improved markdown content

    Returns:
        List of diff sections with type (added/removed/modified/unchanged)
        and line content for original and improved versions.
    """
    heading_re = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)

    def split_sections(text: str) -> list[tuple[str, str]]:
        """Split markdown text into (heading, body) tuples."""
        parts = heading_re.split(text)
        sections: list[tuple[str, str]] = []
        if parts and parts[0].strip():
            sections.append(("(Preamble)", parts[0].strip()))
        for i in range(1, len(parts), 2):
            heading = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections.append((heading, body))
        return sections

    orig_sections = split_sections(original)
    impr_sections = split_sections(improved)

    orig_map = {h: b for h, b in orig_sections}
    seen_headings: set[str] = set()

    changes: list[dict[str, Any]] = []
    for heading, new_body in impr_sections:
        seen_headings.add(heading)
        old_body = orig_map.get(heading)

        if old_body is None:
            changes.append(
                {
                    "section": heading,
                    "type": "added",
                    "original_lines": [],
                    "improved_lines": new_body.splitlines(),
                }
            )
        elif old_body.strip() == new_body.strip():
            changes.append(
                {
                    "section": heading,
                    "type": "unchanged",
                    "original_lines": old_body.splitlines(),
                    "improved_lines": new_body.splitlines(),
                }
            )
        else:
            changes.append(
                {
                    "section": heading,
                    "type": "modified",
                    "original_lines": old_body.splitlines(),
                    "improved_lines": new_body.splitlines(),
                }
            )

    for heading, body in orig_sections:
        if heading not in seen_headings:
            changes.append(
                {
                    "section": heading,
                    "type": "removed",
                    "original_lines": body.splitlines(),
                    "improved_lines": [],
                }
            )

    return changes
