"""
ingestion.py — Build the Neo4j knowledge graph from parsed articles.

Graph schema:
  (:Regulation {id, type, number, title, year})
  (:Article    {id, regulation_id, article_number, text})
  (Article)-[:BELONGS_TO]->(Regulation)
  (Article)-[:REFERENCES]->(Article)

Run:
  python -m src.graph_rag.ingestion
"""
import json
import logging
import re
from typing import Any

from neo4j import GraphDatabase

from src.config import (
    ARTICLES_JSON,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# "PMK 10 TAHUN 2026" → type=PMK, number=10, year=2026
_REG_PATTERN = re.compile(r"^(\w+)\s+(\d+)\s+TAHUN\s+(\d{4})$", re.IGNORECASE)


def _parse_regulation_id(regulation_id: str) -> dict[str, Any]:
    m = _REG_PATTERN.match(regulation_id.strip())
    if m:
        return {"type": m.group(1).upper(), "number": int(m.group(2)), "year": int(m.group(3))}
    return {"type": "UNKNOWN", "number": 0, "year": 0}


def _article_node_id(regulation_id: str, article_number: str) -> str:
    return f"{regulation_id}::{article_number}"


def build_graph(articles_path: str = ARTICLES_JSON) -> None:
    with open(articles_path, encoding="utf-8") as fh:
        articles: list[dict[str, Any]] = json.load(fh)
    logger.info("Loaded %d articles from '%s'.", len(articles), articles_path)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            _create_constraints(session)
            _ingest_articles(session, articles)
            _ingest_references(session, articles)
    finally:
        driver.close()

    logger.info("Graph build complete.")


def _create_constraints(session) -> None:
    session.run(
        "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.id IS UNIQUE"
    )
    logger.info("Constraints ensured.")


def _ingest_articles(session, articles: list[dict[str, Any]]) -> None:
    for article in articles:
        reg_id = article["regulation_id"]
        reg_meta = _parse_regulation_id(reg_id)
        node_id = _article_node_id(reg_id, article["article_number"])

        # Upsert Regulation node
        session.run(
            """
            MERGE (r:Regulation {id: $id})
            ON CREATE SET r.type = $type, r.number = $number, r.year = $year
            """,
            id=reg_id,
            type=reg_meta["type"],
            number=reg_meta["number"],
            year=reg_meta["year"],
        )

        # Upsert Article node
        session.run(
            """
            MERGE (a:Article {id: $id})
            ON CREATE SET
                a.regulation_id    = $regulation_id,
                a.article_number   = $article_number,
                a.text             = $text
            ON MATCH SET
                a.text             = $text
            """,
            id=node_id,
            regulation_id=reg_id,
            article_number=article["article_number"],
            text=article["content"],
        )

        # BELONGS_TO edge
        session.run(
            """
            MATCH (a:Article {id: $article_id}), (r:Regulation {id: $reg_id})
            MERGE (a)-[:BELONGS_TO]->(r)
            """,
            article_id=node_id,
            reg_id=reg_id,
        )

    logger.info("Upserted %d article nodes.", len(articles))


def _ingest_references(session, articles: list[dict[str, Any]]) -> None:
    edge_count = 0
    for article in articles:
        reg_id = article["regulation_id"]
        source_id = _article_node_id(reg_id, article["article_number"])
        refs: list[str] = article.get("references", [])

        for ref_number in refs:
            target_id = _article_node_id(reg_id, ref_number)
            # Only create edge if target node exists
            session.run(
                """
                MATCH (src:Article {id: $src}), (tgt:Article {id: $tgt})
                MERGE (src)-[:REFERENCES]->(tgt)
                """,
                src=source_id,
                tgt=target_id,
            )
            edge_count += 1

    logger.info("Processed %d reference edges.", edge_count)


if __name__ == "__main__":
    build_graph()
