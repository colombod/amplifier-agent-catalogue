"""Agent comparison service for detailed trait analysis."""

import logging
from typing import Any

from agent_catalogue.models.agent import (
    AgentComparison,
    AgentSummary,
    SimilarAgentWithComparison,
    TraitComparison,
)
from agent_catalogue.models.extraction import ExtractedMetadata

logger = logging.getLogger(__name__)


class ComparatorService:
    """Compare agents and generate detailed trait analysis."""

    def compare_traits(
        self,
        trait_name: str,
        new_values: list[str],
        existing_values: list[str],
    ) -> TraitComparison:
        """Compare a single trait between two agents.

        Args:
            trait_name: Name of the trait (e.g., "capabilities")
            new_values: Values from the uploaded agent
            existing_values: Values from the existing agent

        Returns:
            TraitComparison with shared, unique, and overlap ratio
        """
        # Normalize to lowercase for comparison
        new_set = {v.lower().strip() for v in new_values if v}
        existing_set = {v.lower().strip() for v in existing_values if v}

        shared = new_set & existing_set
        only_in_new = new_set - existing_set
        only_in_existing = existing_set - new_set

        # Calculate overlap ratio (Jaccard similarity)
        union = new_set | existing_set
        overlap_ratio = len(shared) / len(union) if union else 0.0

        # Preserve original casing for display
        def find_original(normalized: str, originals: list[str]) -> str:
            for orig in originals:
                if orig.lower().strip() == normalized:
                    return orig
            return normalized

        return TraitComparison(
            trait_name=trait_name,
            shared=[find_original(s, new_values + existing_values) for s in shared],
            only_in_new=[find_original(s, new_values) for s in only_in_new],
            only_in_existing=[find_original(s, existing_values) for s in only_in_existing],
            overlap_ratio=overlap_ratio,
        )

    def compare_agents(
        self,
        new_metadata: ExtractedMetadata,
        existing_agent: AgentSummary,
        existing_metadata: dict[str, Any],
        similarity_score: float,
    ) -> AgentComparison:
        """Generate detailed comparison between new and existing agent.

        Args:
            new_metadata: Extracted metadata from uploaded agent
            existing_agent: Summary of existing agent
            existing_metadata: Full metadata dict from existing agent's version
            similarity_score: Semantic similarity score

        Returns:
            AgentComparison with all trait comparisons
        """
        # Compare each trait
        capabilities = self.compare_traits(
            "capabilities",
            new_metadata.capabilities,
            existing_metadata.get("capabilities", []),
        )

        domains = self.compare_traits(
            "domains",
            new_metadata.domains,
            existing_metadata.get("domains", []),
        )

        tools = self.compare_traits(
            "tools",
            new_metadata.tools,
            existing_metadata.get("tools", []),
        )

        behaviors = self.compare_traits(
            "behaviors",
            new_metadata.behaviors,
            existing_metadata.get("behaviors", []),
        )

        triggers = self.compare_traits(
            "triggers",
            new_metadata.triggers,
            existing_metadata.get("triggers", []),
        )

        # Determine recommendation
        recommendation, reason = self._generate_recommendation(
            similarity_score=similarity_score,
            capabilities=capabilities,
            domains=domains,
            tools=tools,
            new_purpose=new_metadata.purpose,
            existing_purpose=existing_metadata.get("purpose", ""),
        )

        # Compare purposes
        shared_purpose, purpose_comparison = self._compare_purposes(
            new_metadata.purpose,
            existing_metadata.get("purpose", ""),
        )

        return AgentComparison(
            existing_agent=existing_agent,
            similarity_score=similarity_score,
            capabilities=capabilities,
            domains=domains,
            tools=tools,
            behaviors=behaviors,
            triggers=triggers,
            shared_purpose=shared_purpose,
            purpose_comparison=purpose_comparison,
            recommendation=recommendation,
            recommendation_reason=reason,
        )

    def _compare_purposes(
        self,
        new_purpose: str,
        existing_purpose: str,
    ) -> tuple[bool, str]:
        """Compare purposes and generate explanation.

        Returns:
            (shared_purpose: bool, explanation: str)
        """
        if not new_purpose or not existing_purpose:
            return False, "Purpose information incomplete for comparison."

        # Simple keyword overlap check
        new_words = set(new_purpose.lower().split())
        existing_words = set(existing_purpose.lower().split())

        # Remove common words
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "and",
            "but",
            "or",
            "nor",
            "so",
            "yet",
            "both",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "not",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "also",
            "this",
            "that",
            "these",
            "those",
        }

        new_keywords = new_words - stop_words
        existing_keywords = existing_words - stop_words

        shared_keywords = new_keywords & existing_keywords
        overlap = len(shared_keywords) / max(len(new_keywords | existing_keywords), 1)

        if overlap > 0.5:
            return True, (
                f"Both agents appear to address similar problems. "
                f"Shared focus areas: {', '.join(list(shared_keywords)[:5])}."
            )
        elif overlap > 0.2:
            return False, (
                f"Some overlap in purpose. "
                f"Common themes: {', '.join(list(shared_keywords)[:3]) or 'minimal'}."
            )
        else:
            return False, "These agents appear to have different purposes."

    def _generate_recommendation(
        self,
        similarity_score: float,
        capabilities: TraitComparison,
        domains: TraitComparison,
        tools: TraitComparison,
        new_purpose: str,
        existing_purpose: str,
    ) -> tuple[str, str]:
        """Generate a recommendation based on comparison.

        Returns:
            (recommendation: str, reason: str)
        """
        # High similarity + high capability overlap = likely duplicate
        if similarity_score > 0.85 and capabilities.overlap_ratio > 0.7:
            return (
                "likely_duplicate",
                "Very high similarity with significant capability overlap. "
                "This may be a duplicate or minor variant of the existing agent.",
            )

        # High similarity but different capabilities = complementary
        if similarity_score > 0.75 and capabilities.overlap_ratio < 0.3:
            return (
                "complementary",
                "Similar domain but different capabilities. "
                "These agents may complement each other for different use cases.",
            )

        # Same domain, different tools = alternative approach
        if domains.overlap_ratio > 0.7 and tools.overlap_ratio < 0.3:
            return (
                "alternative_approach",
                "Same problem domain but uses different tools. "
                "This offers an alternative approach to similar problems.",
            )

        # Moderate similarity = related
        if similarity_score > 0.6:
            return (
                "related",
                "Moderate similarity suggests these agents are related "
                "but serve distinct purposes. Safe to store separately.",
            )

        # Low similarity = distinct
        return (
            "distinct",
            "Low similarity. This agent appears to be distinct "
            "from existing agents in the catalogue.",
        )

    def build_comparison_results(
        self,
        new_metadata: ExtractedMetadata,
        similar_agents: list[tuple[AgentSummary, float, dict[str, Any]]],
    ) -> list[SimilarAgentWithComparison]:
        """Build detailed comparison results for all similar agents.

        Args:
            new_metadata: Metadata from uploaded agent
            similar_agents: List of (agent_summary, similarity_score, metadata)

        Returns:
            List of SimilarAgentWithComparison with full trait analysis
        """
        results = []

        for agent_summary, similarity_score, existing_metadata in similar_agents:
            comparison = self.compare_agents(
                new_metadata=new_metadata,
                existing_agent=agent_summary,
                existing_metadata=existing_metadata,
                similarity_score=similarity_score,
            )

            # Determine match type
            if similarity_score > 0.9:
                match_type = "near_exact"
            elif similarity_score > 0.75:
                match_type = "high_similarity"
            elif similarity_score > 0.6:
                match_type = "moderate_similarity"
            else:
                match_type = "low_similarity"

            results.append(
                SimilarAgentWithComparison(
                    agent=agent_summary,
                    similarity_score=similarity_score,
                    comparison=comparison,
                    match_type=match_type,
                )
            )

        return results
