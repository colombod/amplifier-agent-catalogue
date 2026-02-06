"""Markdown parsing service for AGENTS.md files."""

import hashlib
import re

from agent_catalogue.models.extraction import ParsedDocument, ParsedSection


class ParserService:
    """Parse AGENTS.md files into structured documents."""

    # Regex for markdown headers
    HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def parse(self, content: str) -> ParsedDocument:
        """Parse markdown content into a structured document.

        Args:
            content: Raw markdown content

        Returns:
            ParsedDocument with extracted sections
        """
        content_hash = self._compute_hash(content)
        sections = self._extract_sections(content)
        title = self._extract_title(sections)

        return ParsedDocument(
            title=title,
            sections=sections,
            raw_content=content,
            content_hash=content_hash,
        )

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _extract_title(self, sections: list[ParsedSection]) -> str | None:
        """Extract title from first h1 header."""
        for section in sections:
            if section.level == 1:
                return section.header
        return None

    def _extract_sections(self, content: str) -> list[ParsedSection]:
        """Extract all sections from markdown content."""
        lines = content.split("\n")
        sections: list[ParsedSection] = []

        # Find all header positions
        header_positions: list[tuple[int, int, str]] = []  # (line_num, level, header)

        for i, line in enumerate(lines):
            match = self.HEADER_PATTERN.match(line)
            if match:
                level = len(match.group(1))
                header = match.group(2).strip()
                header_positions.append((i, level, header))

        # Extract content for each section
        for idx, (line_num, level, header) in enumerate(header_positions):
            # Find end of section (next header of same or higher level, or EOF)
            if idx + 1 < len(header_positions):
                end_line = header_positions[idx + 1][0]
            else:
                end_line = len(lines)

            # Extract content (excluding the header line itself)
            section_lines = lines[line_num + 1 : end_line]
            content_text = "\n".join(section_lines).strip()

            sections.append(
                ParsedSection(
                    header=header,
                    level=level,
                    content=content_text,
                    start_line=line_num + 1,  # 1-indexed
                    end_line=end_line,
                )
            )

        return sections

    def extract_code_blocks(self, content: str) -> list[tuple[str, str]]:
        """Extract fenced code blocks from markdown.

        Returns:
            List of (language, code) tuples
        """
        pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        matches = pattern.findall(content)
        return [(lang or "text", code.strip()) for lang, code in matches]

    def extract_lists(self, content: str) -> list[str]:
        """Extract bullet point items from markdown.

        Returns:
            List of items (without bullet markers)
        """
        pattern = re.compile(r"^[\s]*[-*+]\s+(.+)$", re.MULTILINE)
        return pattern.findall(content)

    def extract_links(self, content: str) -> list[tuple[str, str]]:
        """Extract markdown links.

        Returns:
            List of (text, url) tuples
        """
        pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        return pattern.findall(content)
