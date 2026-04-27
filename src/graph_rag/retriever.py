"""
retriever.py — Two-stage GraphRAG retrieval.

Stage 1 — Vector search (ChromaDB):
    Embed the query and find the top-K semantically similar articles.

Stage 2 — Graph expansion (Neo4j):
    Starting from those seed articles, follow REFERENCES edges up to
    GRAPH_HOP_DEPTH hops and collect all connected articles.

Returns a deduplicated, ranked list of article dicts ready for the generator.
"""
import json
import logging
from typing import Any

import chromadb
from neo4j import GraphDatabase

from src import llm_client
from src.config import (
    CHROMA_DIR,
    CHROMA_COLLECTION,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    TOP_K_VECTOR,
    GRAPH_HOP_DEPTH,
)

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = TOP_K_VECTOR, hop_depth: int = GRAPH_HOP_DEPTH) -> list[dict[str, Any]]:
    """
    Returns a list of article dicts, each with keys:
        id, regulation_id, article_number, text, source ("vector" | "graph")
    """
    seed_articles = _vector_search(query, top_k)
    seed_ids = [a["id"] for a in seed_articles]
    logger.info("Vector search returned %d seed articles: %s", len(seed_ids), seed_ids)

    expanded_articles = _graph_expand(seed_ids, hop_depth)
    logger.info("Graph expansion added %d more articles.", len(expanded_articles))

    return _merge_results(seed_articles, expanded_articles)


# ---------------------------------------------------------------------------
# Stage 1: vector search
# ---------------------------------------------------------------------------
def _vector_search(query: str, top_k: int) -> list[dict[str, Any]]:
    query_embedding = llm_client.embed([query])[0]

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(CHROMA_COLLECTION)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    articles = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        articles.append({
            "id": f"{meta['regulation_id']}::{meta['article_number']}",
            "regulation_id": meta["regulation_id"],
            "article_number": meta["article_number"],
            "text": doc,
            "references": json.loads(meta.get("references", "[]")),
            "score": 1.0 - dist,  # cosine similarity
            "source": "vector",
        })

    return articles


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
