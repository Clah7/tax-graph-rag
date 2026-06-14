"""
retriever.py — Two-stage GraphRAG retrieval.

Stage 1 — Vector search (ChromaDB):
    Embed the query and find the top-K semantically similar articles.
    Delegated to src.vector_search so the step is bit-for-bit identical
    to BaselineRAG.

Stage 2 — Graph expansion (Neo4j):
    Starting from those seed articles, follow REFERENCES edges up to
    GRAPH_HOP_DEPTH hops and collect all connected articles.

Returns a deduplicated, ranked list of article dicts ready for the generator.
"""
import logging
from typing import Any

from neo4j import GraphDatabase

from src.config import (
    GRAPH_HOP_DEPTH,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    TOP_K_VECTOR,
)
from src.vector_search import vector_search

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = TOP_K_VECTOR, hop_depth: int = GRAPH_HOP_DEPTH) -> list[dict[str, Any]]:
    """
    Returns a list of article dicts, each with keys:
        id, regulation_id, article_number, text, source ("vector" | "graph")
    """
    seed_articles = vector_search(query, top_k)
    seed_ids = [a["id"] for a in seed_articles]
    logger.info("Vector search returned %d seed articles: %s", len(seed_ids), seed_ids)

    expanded_articles = _graph_expand(seed_ids, hop_depth)
    logger.info("Graph expansion added %d more articles.", len(expanded_articles))

    return _merge_results(seed_articles, expanded_articles)


# ---------------------------------------------------------------------------
# Stage 2: graph expansion
# ---------------------------------------------------------------------------
def _graph_expand(seed_ids: list[str], hop_depth: int) -> list[dict[str, Any]]:
    if not seed_ids:
        return []

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            records = session.run(
                f"""
                UNWIND $seed_ids AS seed
                MATCH (src:Article {{id: seed}})
                MATCH (src)-[:REFERENCES*1..{hop_depth}]-(neighbor:Article)
                WHERE NOT neighbor.id IN $seed_ids
                RETURN DISTINCT
                    neighbor.id             AS id,
                    neighbor.regulation_id  AS regulation_id,
                    neighbor.article_number AS article_number,
                    neighbor.text           AS text
                """,
                seed_ids=seed_ids,
            )
            articles = []
            for r in records:
                articles.append({
                    "id": r["id"],
                    "regulation_id": r["regulation_id"],
                    "article_number": r["article_number"],
                    "text": r["text"],
                    "references": [],
                    "score": 0.0,
                    "source": "graph",
                })
    finally:
        driver.close()

    return articles


# ---------------------------------------------------------------------------
# Merge: seeds first, then graph-expanded, deduplicated
# ---------------------------------------------------------------------------
def _merge_results(
    seed_articles: list[dict[str, Any]],
    expanded_articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged = []
    for article in seed_articles + expanded_articles:
        if article["id"] not in seen:
            seen.add(article["id"])
            merged.append(article)
    return merged
