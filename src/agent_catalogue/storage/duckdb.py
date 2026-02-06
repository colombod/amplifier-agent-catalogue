"""DuckDB storage repository for Agent Catalogue."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import duckdb

from agent_catalogue.config import StorageConfig, get_config
from agent_catalogue.models.agent import (
    Agent,
    AgentSummary,
    AgentVersion,
    SearchResult,
    SimilarAgent,
)

logger = logging.getLogger(__name__)


class DuckDBRepository:
    """DuckDB-based storage for agents and versions."""

    SCHEMA_VERSION = 2

    def __init__(self, config: StorageConfig | None = None):
        """Initialize the repository.

        Args:
            config: Storage configuration. Uses global config if not provided.
        """
        self.config = config or get_config().storage
        self._ensure_db_directory()
        # Single persistent connection - DuckDB does not support concurrent
        # connections to the same file.  The Amplifier orchestrator runs tools
        # in parallel (asyncio.gather), so every tool call that touches the DB
        # must go through this single connection.
        self._conn = duckdb.connect(str(self.config.db_path))
        self._init_schema()

    def _ensure_db_directory(self) -> None:
        """Ensure the database directory exists."""
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Get the database connection.

        Uses a single persistent connection instead of opening a new one
        per call.  DuckDB holds a write-lock on the file, so concurrent
        duckdb.connect() calls from parallel tool execution would fail.
        """
        yield self._conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    slug VARCHAR UNIQUE NOT NULL,
                    description VARCHAR DEFAULT '',
                    current_version_id VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_versions (
                    id VARCHAR PRIMARY KEY,
                    agent_id VARCHAR NOT NULL REFERENCES agents(id),
                    version_number INTEGER NOT NULL,
                    raw_content TEXT NOT NULL,
                    content_hash VARCHAR NOT NULL,
                    embedding DOUBLE[],
                    metadata JSON,
                    change_summary VARCHAR,
                    token_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_id, version_number)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_versions_agent 
                ON agent_versions(agent_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agents_slug 
                ON agents(slug)
            """)

            # Schema version tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    key VARCHAR PRIMARY KEY,
                    value VARCHAR
                )
            """)

            # Run migrations for existing databases
            self._migrate(conn)

            conn.execute(
                """
                INSERT OR REPLACE INTO schema_info (key, value) 
                VALUES ('version', ?)
            """,
                [str(self.SCHEMA_VERSION)],
            )

    def _migrate(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Run schema migrations for existing databases."""
        # v2: add token_count column to agent_versions
        try:
            conn.execute("ALTER TABLE agent_versions ADD COLUMN token_count INTEGER")
            logger.info("Migration v2: added token_count column to agent_versions")
        except duckdb.CatalogException:
            pass  # Column already exists

    # ==================== Agent Operations ====================

    def create_agent(self, agent: Agent) -> Agent:
        """Create a new agent."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agents (id, name, slug, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                [
                    str(agent.id),
                    agent.name,
                    agent.slug,
                    agent.description,
                    agent.created_at,
                    agent.updated_at,
                ],
            )
        return agent

    def get_agent(self, agent_id: UUID) -> Agent | None:
        """Get an agent by ID."""
        with self._connection() as conn:
            result = conn.execute(
                """
                SELECT id, name, slug, description, current_version_id, 
                       created_at, updated_at
                FROM agents WHERE id = ?
            """,
                [str(agent_id)],
            ).fetchone()

            if not result:
                return None

            return self._row_to_agent(result)

    def get_agent_by_slug(self, slug: str) -> Agent | None:
        """Get an agent by slug."""
        with self._connection() as conn:
            result = conn.execute(
                """
                SELECT id, name, slug, description, current_version_id,
                       created_at, updated_at
                FROM agents WHERE slug = ?
            """,
                [slug],
            ).fetchone()

            if not result:
                return None

            return self._row_to_agent(result)

    def list_agents(
        self,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
    ) -> list[AgentSummary]:
        """List agents with optional search."""
        with self._connection() as conn:
            if search:
                # Simple text search on name and description
                query = """
                    SELECT a.id, a.name, a.slug, a.description, a.updated_at,
                           COUNT(v.id) as version_count,
                           COALESCE(MAX(v.version_number), 0) as current_version,
                           MAX(v.metadata) as metadata,
                           (SELECT cv.token_count FROM agent_versions cv
                            WHERE cv.id = a.current_version_id) as token_count
                    FROM agents a
                    LEFT JOIN agent_versions v ON a.id = v.agent_id
                    WHERE LOWER(a.name) LIKE ? OR LOWER(a.description) LIKE ?
                    GROUP BY a.id, a.name, a.slug, a.description,
                             a.updated_at, a.current_version_id
                    ORDER BY a.updated_at DESC
                    LIMIT ? OFFSET ?
                """
                search_pattern = f"%{search.lower()}%"
                results = conn.execute(
                    query, [search_pattern, search_pattern, limit, offset]
                ).fetchall()
            else:
                query = """
                    SELECT a.id, a.name, a.slug, a.description, a.updated_at,
                           COUNT(v.id) as version_count,
                           COALESCE(MAX(v.version_number), 0) as current_version,
                           MAX(v.metadata) as metadata,
                           (SELECT cv.token_count FROM agent_versions cv
                            WHERE cv.id = a.current_version_id) as token_count
                    FROM agents a
                    LEFT JOIN agent_versions v ON a.id = v.agent_id
                    GROUP BY a.id, a.name, a.slug, a.description,
                             a.updated_at, a.current_version_id
                    ORDER BY a.updated_at DESC
                    LIMIT ? OFFSET ?
                """
                results = conn.execute(query, [limit, offset]).fetchall()

            return [self._row_to_agent_summary(row) for row in results]

    def update_agent(self, agent: Agent) -> Agent:
        """Update an agent."""
        agent.updated_at = datetime.utcnow()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE agents
                SET name = ?, slug = ?, description = ?, 
                    current_version_id = ?, updated_at = ?
                WHERE id = ?
            """,
                [
                    agent.name,
                    agent.slug,
                    agent.description,
                    str(agent.current_version_id) if agent.current_version_id else None,
                    agent.updated_at,
                    str(agent.id),
                ],
            )
        return agent

    def delete_agent(self, agent_id: UUID) -> bool:
        """Delete an agent and all its versions."""
        with self._connection() as conn:
            # Delete versions first
            conn.execute("DELETE FROM agent_versions WHERE agent_id = ?", [str(agent_id)])
            # Delete agent
            result = conn.execute("DELETE FROM agents WHERE id = ?", [str(agent_id)])
            return result.rowcount > 0

    # ==================== Version Operations ====================

    def create_version(self, version: AgentVersion) -> AgentVersion:
        """Create a new version for an agent."""
        with self._connection() as conn:
            # Get next version number
            result = conn.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM agent_versions WHERE agent_id = ?
            """,
                [str(version.agent_id)],
            ).fetchone()
            version.version_number = result[0] if result else 1

            conn.execute(
                """
                INSERT INTO agent_versions 
                (id, agent_id, version_number, raw_content, content_hash,
                 embedding, metadata, change_summary, token_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    str(version.id),
                    str(version.agent_id),
                    version.version_number,
                    version.raw_content,
                    version.content_hash,
                    version.embedding,
                    json.dumps(version.metadata) if version.metadata else None,
                    version.change_summary,
                    version.token_count,
                    version.created_at,
                ],
            )

            # Update agent's current version
            conn.execute(
                """
                UPDATE agents 
                SET current_version_id = ?, updated_at = ?
                WHERE id = ?
            """,
                [str(version.id), datetime.utcnow(), str(version.agent_id)],
            )

        return version

    def get_version(self, version_id: UUID) -> AgentVersion | None:
        """Get a specific version."""
        with self._connection() as conn:
            result = conn.execute(
                """
                SELECT id, agent_id, version_number, raw_content, content_hash,
                       embedding, metadata, change_summary, token_count, created_at
                FROM agent_versions WHERE id = ?
            """,
                [str(version_id)],
            ).fetchone()

            if not result:
                return None

            return self._row_to_version(result)

    def get_versions(self, agent_id: UUID) -> list[AgentVersion]:
        """Get all versions of an agent."""
        with self._connection() as conn:
            results = conn.execute(
                """
                SELECT id, agent_id, version_number, raw_content, content_hash,
                       embedding, metadata, change_summary, token_count, created_at
                FROM agent_versions 
                WHERE agent_id = ?
                ORDER BY version_number DESC
            """,
                [str(agent_id)],
            ).fetchall()

            return [self._row_to_version(row) for row in results]

    def get_version_by_number(self, agent_id: UUID, version_number: int) -> AgentVersion | None:
        """Get a specific version by agent ID and version number."""
        with self._connection() as conn:
            result = conn.execute(
                """
                SELECT id, agent_id, version_number, raw_content, content_hash,
                       embedding, metadata, change_summary, token_count, created_at
                FROM agent_versions 
                WHERE agent_id = ? AND version_number = ?
            """,
                [str(agent_id), version_number],
            ).fetchone()

            if not result:
                return None

            return self._row_to_version(result)

    def get_latest_version(self, agent_id: UUID) -> AgentVersion | None:
        """Get the latest version of an agent."""
        with self._connection() as conn:
            result = conn.execute(
                """
                SELECT id, agent_id, version_number, raw_content, content_hash,
                       embedding, metadata, change_summary, token_count, created_at
                FROM agent_versions 
                WHERE agent_id = ?
                ORDER BY version_number DESC
                LIMIT 1
            """,
                [str(agent_id)],
            ).fetchone()

            if not result:
                return None

            return self._row_to_version(result)

    # ==================== Search & Similarity ====================

    def find_by_content_hash(self, content_hash: str) -> AgentVersion | None:
        """Find a version by content hash (exact duplicate detection)."""
        with self._connection() as conn:
            result = conn.execute(
                """
                SELECT id, agent_id, version_number, raw_content, content_hash,
                       embedding, metadata, change_summary, token_count, created_at
                FROM agent_versions WHERE content_hash = ?
                LIMIT 1
            """,
                [content_hash],
            ).fetchone()

            if not result:
                return None

            return self._row_to_version(result)

    def find_similar(
        self,
        embedding: list[float],
        threshold: float = 0.7,
        limit: int = 10,
        exclude_agent_id: UUID | None = None,
    ) -> list[SimilarAgent]:
        """Find similar agents using vector similarity.

        Uses cosine similarity computed in DuckDB.
        """
        with self._connection() as conn:
            # Build exclusion clause
            exclude_clause = ""
            params: list[Any] = [embedding]  # For cosine similarity
            if exclude_agent_id:
                exclude_clause = "AND a.id != ?"
                params.append(str(exclude_agent_id))
            params.extend([threshold, limit])

            # Compute cosine similarity using DuckDB array functions
            query = f"""
                WITH similarity_scores AS (
                    SELECT 
                        a.id, a.name, a.slug, a.description, a.updated_at,
                        v.version_number,
                        v.metadata,
                        list_cosine_similarity(v.embedding, ?::DOUBLE[]) as similarity
                    FROM agents a
                    JOIN agent_versions v ON a.current_version_id = v.id
                    WHERE v.embedding IS NOT NULL
                    {exclude_clause}
                )
                SELECT id, name, slug, description, updated_at, 
                       version_number, metadata, similarity
                FROM similarity_scores
                WHERE similarity >= ?
                ORDER BY similarity DESC
                LIMIT ?
            """

            results = conn.execute(query, params).fetchall()

            similar_agents = []
            for row in results:
                metadata = json.loads(row[6]) if row[6] else {}
                summary = AgentSummary(
                    id=UUID(row[0]),
                    name=row[1],
                    slug=row[2],
                    description=row[3],
                    updated_at=row[4],
                    version_count=1,  # Simplified for this query
                    current_version=row[5],
                    domains=metadata.get("domains", []),
                    capabilities=metadata.get("capabilities", []),
                )
                similar_agents.append(
                    SimilarAgent(
                        agent=summary,
                        similarity_score=row[7],
                        match_type="semantic",
                        matched_on=[],
                    )
                )

            return similar_agents

    def find_similar_with_metadata(
        self,
        embedding: list[float],
        threshold: float = 0.7,
        limit: int = 10,
        exclude_agent_id: UUID | None = None,
    ) -> list[tuple[AgentSummary, float, dict]]:
        """Find similar agents with full metadata for comparison.

        Returns list of (AgentSummary, similarity_score, metadata_dict) tuples.
        """
        with self._connection() as conn:
            exclude_clause = ""
            params: list[Any] = [embedding]  # For cosine similarity
            if exclude_agent_id:
                exclude_clause = "AND a.id != ?"
                params.append(str(exclude_agent_id))
            params.extend([threshold, limit])

            query = f"""
                WITH similarity_scores AS (
                    SELECT 
                        a.id, a.name, a.slug, a.description, a.updated_at,
                        v.version_number,
                        v.metadata,
                        list_cosine_similarity(v.embedding, ?::DOUBLE[]) as similarity
                    FROM agents a
                    JOIN agent_versions v ON a.current_version_id = v.id
                    WHERE v.embedding IS NOT NULL
                    {exclude_clause}
                )
                SELECT id, name, slug, description, updated_at, 
                       version_number, metadata, similarity
                FROM similarity_scores
                WHERE similarity >= ?
                ORDER BY similarity DESC
                LIMIT ?
            """

            results = conn.execute(query, params).fetchall()

            similar_with_metadata = []
            for row in results:
                metadata = json.loads(row[6]) if row[6] else {}
                summary = AgentSummary(
                    id=UUID(row[0]),
                    name=row[1],
                    slug=row[2],
                    description=row[3],
                    updated_at=row[4],
                    version_count=1,
                    current_version=row[5],
                    domains=metadata.get("domains", []),
                    capabilities=metadata.get("capabilities", []),
                )
                similar_with_metadata.append((summary, row[7], metadata))

            return similar_with_metadata

    def search(
        self,
        query_embedding: list[float],
        query_text: str | None = None,
        domains: list[str] | None = None,
        tools: list[str] | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search for agents using semantic similarity and optional facets."""
        with self._connection() as conn:
            # Base query with semantic similarity
            query = """
                WITH semantic_scores AS (
                    SELECT 
                        a.id, a.name, a.slug, a.description, a.updated_at,
                        v.version_number,
                        v.metadata,
                        list_cosine_similarity(v.embedding, ?::DOUBLE[]) as semantic_score
                    FROM agents a
                    JOIN agent_versions v ON a.current_version_id = v.id
                    WHERE v.embedding IS NOT NULL
                )
                SELECT id, name, slug, description, updated_at,
                       version_number, metadata, semantic_score
                FROM semantic_scores
                WHERE semantic_score > 0.3
                ORDER BY semantic_score DESC
                LIMIT ?
            """

            results = conn.execute(query, [query_embedding, limit]).fetchall()

            search_results = []
            for row in results:
                metadata = json.loads(row[6]) if row[6] else {}

                # Check facet matches
                facet_matches = []
                if domains:
                    agent_domains = set(d.lower() for d in metadata.get("domains", []))
                    matched_domains = agent_domains & set(d.lower() for d in domains)
                    facet_matches.extend(matched_domains)
                if tools:
                    agent_tools = set(t.lower() for t in metadata.get("tools", []))
                    matched_tools = agent_tools & set(t.lower() for t in tools)
                    facet_matches.extend(matched_tools)

                # Calculate combined score (boost for facet matches)
                semantic_score = row[7]
                facet_boost = len(facet_matches) * 0.1
                combined_score = min(1.0, semantic_score + facet_boost)

                summary = AgentSummary(
                    id=UUID(row[0]),
                    name=row[1],
                    slug=row[2],
                    description=row[3],
                    updated_at=row[4],
                    version_count=1,
                    current_version=row[5],
                    domains=metadata.get("domains", []),
                    capabilities=metadata.get("capabilities", []),
                )

                search_results.append(
                    SearchResult(
                        agent=summary,
                        score=combined_score,
                        semantic_score=semantic_score,
                        facet_matches=facet_matches,
                        explanation=f"Semantic match: {semantic_score:.2f}",
                        capabilities_matched=metadata.get("capabilities", [])[:3],
                    )
                )

            # Re-sort by combined score
            search_results.sort(key=lambda x: x.score, reverse=True)
            return search_results

    # ==================== Helper Methods ====================

    def _row_to_agent(self, row: tuple) -> Agent:
        """Convert a database row to an Agent model."""
        return Agent(
            id=UUID(row[0]),
            name=row[1],
            slug=row[2],
            description=row[3] or "",
            current_version_id=UUID(row[4]) if row[4] else None,
            created_at=row[5],
            updated_at=row[6],
        )

    def _row_to_agent_summary(self, row: tuple) -> AgentSummary:
        """Convert a database row to an AgentSummary model."""
        metadata = json.loads(row[7]) if row[7] else {}
        return AgentSummary(
            id=UUID(row[0]),
            name=row[1],
            slug=row[2],
            description=row[3] or "",
            updated_at=row[4],
            version_count=row[5],
            current_version=row[6],
            domains=metadata.get("domains", []),
            capabilities=metadata.get("capabilities", []),
            token_count=row[8] if len(row) > 8 else None,
        )

    def _row_to_version(self, row: tuple) -> AgentVersion:
        """Convert a database row to an AgentVersion model."""
        return AgentVersion(
            id=UUID(row[0]),
            agent_id=UUID(row[1]),
            version_number=row[2],
            raw_content=row[3],
            content_hash=row[4],
            embedding=list(row[5]) if row[5] else None,
            metadata=json.loads(row[6]) if row[6] else {},
            change_summary=row[7],
            token_count=row[8],
            created_at=row[9],
        )

    def count_agents(self) -> int:
        """Get total number of agents."""
        with self._connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM agents").fetchone()
            return result[0] if result else 0
