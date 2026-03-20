"""
Neo4j Knowledge Graph Service
Handles all graph database operations: create, query, traverse, analyze
"""
import json
from typing import Any, Optional
from loguru import logger
from neo4j import AsyncGraphDatabase, AsyncDriver
from config import get_settings

settings = get_settings()


class GraphService:
    """Neo4j-backed Knowledge Graph service"""

    def __init__(self):
        self.driver: Optional[AsyncDriver] = None
        self.database = settings.neo4j_database
        logger.info(f"GraphService configured for Neo4j: {settings.neo4j_uri}")

    async def connect(self):
        """Initialize Neo4j async driver"""
        try:
            self.driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
            )
            # Test connection
            async with self.driver.session(database=self.database) as session:
                result = await session.run("RETURN 1 AS test")
                await result.single()
            logger.success("✅ Neo4j connected successfully")
            await self._create_indexes()
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise

    async def close(self):
        if self.driver:
            await self.driver.close()

    async def _create_indexes(self):
        """Create indexes for better performance"""
        queries = [
            "CREATE INDEX concept_user IF NOT EXISTS FOR (c:Concept) ON (c.user_id)",
            "CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name)",
            "CREATE INDEX concept_session IF NOT EXISTS FOR (c:Concept) ON (c.session_id)",
        ]
        async with self.driver.session(database=self.database) as session:
            for q in queries:
                try:
                    await session.run(q)
                except Exception as e:
                    logger.warning(f"Index creation: {e}")

    # ─── Write Operations ──────────────────────────────────────────────────

    async def store_knowledge(
        self,
        user_id: int,
        session_id: str,
        concepts: list[dict],
        relationships: list[dict],
        domain: str,
    ) -> dict[str, int]:
        """Store extracted knowledge graph in Neo4j"""
        nodes_created = 0
        rels_created = 0

        async with self.driver.session(database=self.database) as session:
            # Create/merge concepts
            for concept in concepts:
                name = concept.get("name", "").strip()
                if not name:
                    continue
                query = """
                MERGE (c:Concept {name: $name, user_id: $user_id})
                ON CREATE SET
                    c.type = $type,
                    c.description = $description,
                    c.importance = $importance,
                    c.domain = $domain,
                    c.session_id = $session_id,
                    c.created_at = datetime()
                ON MATCH SET
                    c.importance = CASE
                        WHEN $importance > c.importance THEN $importance
                        ELSE c.importance
                    END,
                    c.last_seen = datetime()
                RETURN c
                """
                await session.run(
                    query,
                    name=name,
                    user_id=str(user_id),
                    type=concept.get("type", "ENTITY"),
                    description=concept.get("description", ""),
                    importance=concept.get("importance", 5),
                    domain=domain,
                    session_id=session_id,
                )
                nodes_created += 1

            # Create relationships
            for rel in relationships:
                src = rel.get("source", "").strip()
                tgt = rel.get("target", "").strip()
                relation = rel.get("relation", "related_to").upper().replace(" ", "_")
                if not src or not tgt:
                    continue
                query = f"""
                MATCH (a:Concept {{name: $source, user_id: $user_id}})
                MATCH (b:Concept {{name: $target, user_id: $user_id}})
                MERGE (a)-[r:{relation}]->(b)
                ON CREATE SET
                    r.description = $description,
                    r.confidence = $confidence,
                    r.created_at = datetime()
                RETURN r
                """
                try:
                    await session.run(
                        query,
                        source=src,
                        target=tgt,
                        user_id=str(user_id),
                        description=rel.get("description", ""),
                        confidence=rel.get("confidence", 0.8),
                    )
                    rels_created += 1
                except Exception as e:
                    logger.warning(f"Relationship creation failed ({src}→{tgt}): {e}")

        logger.success(f"Stored: {nodes_created} nodes, {rels_created} relationships for user {user_id}")
        return {"nodes": nodes_created, "relationships": rels_created}

    # ─── Read Operations ────────────────────────────────────────────────────

    async def get_user_graph(self, user_id: int) -> dict[str, Any]:
        """Get all nodes and relationships for a user"""
        async with self.driver.session(database=self.database) as session:
            # Get nodes
            node_result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                RETURN c.name AS name, c.type AS type, c.description AS description,
                       c.importance AS importance, c.domain AS domain
                ORDER BY c.importance DESC
                LIMIT 200
                """,
                user_id=str(user_id),
            )
            nodes = [dict(r) async for r in node_result]

            # Get relationships
            rel_result = await session.run(
                """
                MATCH (a:Concept {user_id: $user_id})-[r]->(b:Concept {user_id: $user_id})
                RETURN a.name AS source, type(r) AS relation,
                       b.name AS target, r.description AS description,
                       r.confidence AS confidence
                LIMIT 500
                """,
                user_id=str(user_id),
            )
            relationships = [dict(r) async for r in rel_result]

        return {"nodes": nodes, "relationships": relationships}

    async def find_path(
        self, user_id: int, source: str, target: str, max_depth: int = 5
    ) -> list[dict]:
        """Find shortest path between two concepts"""
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                f"""
                MATCH path = shortestPath(
                    (a:Concept {{name: $source, user_id: $user_id}})-[*1..{max_depth}]-
                    (b:Concept {{name: $target, user_id: $user_id}})
                )
                RETURN [node IN nodes(path) | node.name] AS nodes,
                       [rel IN relationships(path) | type(rel)] AS rels,
                       length(path) AS path_length
                LIMIT 3
                """,
                source=source,
                target=target,
                user_id=str(user_id),
            )
            paths = [dict(r) async for r in result]
        return paths

    async def get_node_neighbors(
        self, user_id: int, concept_name: str, depth: int = 1
    ) -> dict[str, Any]:
        """Get neighbors of a concept"""
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (c:Concept {name: $name, user_id: $user_id})-[r]-(neighbor:Concept)
                RETURN neighbor.name AS name, neighbor.type AS type,
                       type(r) AS relation, neighbor.importance AS importance
                ORDER BY neighbor.importance DESC
                LIMIT 20
                """,
                name=concept_name,
                user_id=str(user_id),
            )
            neighbors = [dict(r) async for r in result]

        return {"concept": concept_name, "neighbors": neighbors}

    async def analyze_graph_structure(self, user_id: int) -> dict[str, Any]:
        """Analyze graph structure: centrality, isolated nodes, weak areas"""
        async with self.driver.session(database=self.database) as session:
            # Total stats
            stats_result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                OPTIONAL MATCH (c)-[r]->()
                WITH c, count(r) AS out_degree
                RETURN
                    count(c) AS total_nodes,
                    sum(out_degree) AS total_edges,
                    avg(out_degree) AS avg_degree,
                    max(out_degree) AS max_degree,
                    count(CASE WHEN out_degree = 0 THEN 1 END) AS isolated_count
                """,
                user_id=str(user_id),
            )
            stats = dict(await stats_result.single() or {})

            # Most connected nodes (hub concepts)
            hub_result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                OPTIONAL MATCH (c)-[r]-()
                WITH c, count(r) AS degree
                ORDER BY degree DESC
                LIMIT 10
                RETURN c.name AS name, c.type AS type, degree
                """,
                user_id=str(user_id),
            )
            hubs = [dict(r) async for r in hub_result]

            # Isolated concepts
            isolated_result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                WHERE NOT (c)-[]-()
                RETURN c.name AS name, c.type AS type
                LIMIT 20
                """,
                user_id=str(user_id),
            )
            isolated = [dict(r) async for r in isolated_result]

            # Domain distribution
            domain_result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                RETURN c.domain AS domain, count(c) AS count
                ORDER BY count DESC
                LIMIT 10
                """,
                user_id=str(user_id),
            )
            domains = [dict(r) async for r in domain_result]

        return {
            "stats": stats,
            "hub_concepts": hubs,
            "isolated_concepts": isolated,
            "domains": domains,
        }

    async def search_concepts(self, user_id: int, query: str) -> list[dict]:
        """Search for concepts by name (case-insensitive)"""
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                WHERE toLower(c.name) CONTAINS toLower($query)
                RETURN c.name AS name, c.type AS type, c.description AS description,
                       c.importance AS importance
                ORDER BY c.importance DESC
                LIMIT 10
                """,
                user_id=str(user_id),
                query=query,
            )
            return [dict(r) async for r in result]

    async def delete_user_graph(self, user_id: int) -> int:
        """Delete all data for a user"""
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (c:Concept {user_id: $user_id})
                DETACH DELETE c
                RETURN count(c) AS deleted
                """,
                user_id=str(user_id),
            )
            record = await result.single()
            deleted = record["deleted"] if record else 0
        logger.info(f"Deleted {deleted} nodes for user {user_id}")
        return deleted

    async def get_node_list(self, user_id: int) -> list[str]:
        """Get list of all concept names for a user"""
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                "MATCH (c:Concept {user_id: $user_id}) RETURN c.name AS name ORDER BY c.name",
                user_id=str(user_id),
            )
            return [r["name"] async for r in result]
