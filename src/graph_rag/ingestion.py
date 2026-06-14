"""
ingestion.py — Build the Neo4j knowledge graph from parsed articles.

Graph schema:
  (:Regulation {id, type, number, year, title, category})
  (:Article    {id, regulation_id, article_number, text})
  (:Concept    {name})

  (Article)-[:BELONGS_TO]->(Regulation)
  (Article)-[:REFERENCES {ayat}]->(Article)
    ayat is the target clause number as a string, or "" when the reference
    is to the whole Pasal. Distinct ayat values produce distinct edges.
  (Regulation)-[:AMENDS {action}]->(Regulation)
    action is "amends" or "repeals" (from the regulation title).
  (Article)-[:DEFINES]->(Concept)
    Created when an article (typically Pasal 1) introduces a defined term
    via the standard "Term [yang selanjutnya disebut/disingkat X,] adalah ..."
    pattern. Concepts are MERGEd by name so a term defined in many
    regulations becomes a hub node.

Inputs:
  data/processed/articles.json     — list of article dicts
  data/processed/regulations.json  — list of regulation dicts (title, amends, ...)

Run:
  python -m src.graph_rag.ingestion
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from src.config import (
    ARTICLES_JSON,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Sibling of ARTICLES_JSON — emitted by parser.parse_all alongside articles.json.
REGULATIONS_JSON: str = str(Path(ARTICLES_JSON).with_name("regulations.json"))

# "PMK 10 TAHUN 2026" → type=PMK, number=10, year=2026
_REG_PATTERN = re.compile(r"^(\w+)\s+(\d+)\s+TAHUN\s+(\d{4})$", re.IGNORECASE)


def _parse_regulation_id(regulation_id: str) -> dict[str, Any]:
    m = _REG_PATTERN.match(regulation_id.strip())
    if m:
        return {"type": m.group(1).upper(), "number": int(m.group(2)), "year": int(m.group(3))}
    return {"type": "UNKNOWN", "number": 0, "year": 0}


def _article_node_id(regulation_id: str, article_number: str) -> str:
    return f"{regulation_id}::{article_number}"


def build_graph(
    articles_path: str = ARTICLES_JSON,
    regulations_path: str = REGULATIONS_JSON,
) -> None:
    with open(articles_path, encoding="utf-8") as fh:
        articles: list[dict[str, Any]] = json.load(fh)
    logger.info("Loaded %d articles from '%s'.", len(articles), articles_path)

    regulations: list[dict[str, Any]] = []
    if Path(regulations_path).exists():
        with open(regulations_path, encoding="utf-8") as fh:
            regulations = json.load(fh)
        logger.info("Loaded %d regulations from '%s'.", len(regulations), regulations_path)
    else:
        logger.warning(
            "regulations.json not found at '%s' — AMENDS edges will not be created. "
            "Re-run parser.parse_all to generate it.",
            regulations_path,
        )

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            _create_constraints(session)
            _ingest_regulations(session, regulations)
            _ingest_articles(session, articles)
            _ingest_references(session, articles)
            _ingest_definitions(session, articles)
    finally:
        driver.close()

    logger.info("Graph build complete.")


def _create_constraints(session) -> None:
    session.run(
        "CREATE CONSTRAINT article_id IF NOT EXISTS "
        "FOR (a:Article) REQUIRE a.id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT regulation_id IF NOT EXISTS "
        "FOR (r:Regulation) REQUIRE r.id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT concept_name IF NOT EXISTS "
        "FOR (c:Concept) REQUIRE c.name IS UNIQUE"
    )
    logger.info("Constraints ensured.")


def _ingest_regulations(session, regulations: list[dict[str, Any]]) -> None:
    """
    Pre-create Regulation nodes with full metadata (title, category, dates) and
    build AMENDS edges. Amendment TARGETS may not be in our corpus, but we
    still create stub Regulation nodes for them so the AMENDS edge is queryable.
    """
    if not regulations:
        return

    for reg in regulations:
        reg_id = reg["regulation_id"]
        reg_meta = _parse_regulation_id(reg_id)
        session.run(
            """
            MERGE (r:Regulation {id: $id})
            ON CREATE SET r.type = $type, r.number = $number, r.year = $year,
                          r.title = $title, r.category = $category,
                          r.date_enacted = $date_enacted,
                          r.date_promulgated = $date_promulgated
            ON MATCH  SET r.title = $title, r.category = $category,
                          r.date_enacted = $date_enacted,
                          r.date_promulgated = $date_promulgated
            """,
            id=reg_id,
            type=reg_meta["type"],
            number=reg_meta["number"],
            year=reg_meta["year"],
            title=reg.get("title", ""),
            category=reg.get("category", ""),
            date_enacted=reg.get("date_enacted", ""),
            date_promulgated=reg.get("date_promulgated", ""),
        )

    amends_count = 0
    for reg in regulations:
        src_id = reg["regulation_id"]
        for ref in reg.get("amends", []):
            target_id = ref["regulation_id"]
            target_meta = _parse_regulation_id(target_id)
            # Stub-create the target if it isn't already a known regulation.
            session.run(
                """
                MERGE (r:Regulation {id: $id})
                ON CREATE SET r.type = $type, r.number = $number, r.year = $year
                """,
                id=target_id,
                type=target_meta["type"],
                number=target_meta["number"],
                year=target_meta["year"],
            )
            session.run(
                """
                MATCH (src:Regulation {id: $src}), (tgt:Regulation {id: $tgt})
                MERGE (src)-[a:AMENDS {action: $action}]->(tgt)
                """,
                src=src_id,
                tgt=target_id,
                action=ref["action"],
            )
            amends_count += 1

    logger.info("Upserted %d regulations and %d AMENDS edges.", len(regulations), amends_count)


def _ingest_articles(session, articles: list[dict[str, Any]]) -> None:
    for article in articles:
        reg_id = article["regulation_id"]
        reg_meta = _parse_regulation_id(reg_id)
        node_id = _article_node_id(reg_id, article["article_number"])

        # Upsert Regulation node (no-op if already created by _ingest_regulations).
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
    intra_count = 0
    inter_count = 0

    for article in articles:
        reg_id    = article["regulation_id"]
        source_id = _article_node_id(reg_id, article["article_number"])

        # Intra-regulation edges (same regulation)
        for ref in article.get("references", []):
            target_id = _article_node_id(reg_id, ref["article"])
            ayat = ref.get("ayat") or ""
            session.run(
                """
                MATCH (src:Article {id: $src}), (tgt:Article {id: $tgt})
                MERGE (src)-[:REFERENCES {ayat: $ayat}]->(tgt)
                """,
                src=source_id,
                tgt=target_id,
                ayat=ayat,
            )
            intra_count += 1

        # Inter-regulation edges (cross-regulation)
        for ref in article.get("cross_regulation_references", []):
            target_id = _article_node_id(ref["regulation_id"], ref["article_number"])
            ayat = ref.get("ayat") or ""
            session.run(
                """
                MATCH (src:Article {id: $src}), (tgt:Article {id: $tgt})
                MERGE (src)-[:REFERENCES {ayat: $ayat}]->(tgt)
                """,
                src=source_id,
                tgt=target_id,
                ayat=ayat,
            )
            inter_count += 1

    logger.info(
        "Processed %d intra-regulation + %d cross-regulation reference edges.",
        intra_count, inter_count,
    )


def _ingest_definitions(session, articles: list[dict[str, Any]]) -> None:
    """
    Create Concept nodes and (Article)-[:DEFINES]->(Concept) edges from the
    `defines` field on articles. Concepts are MERGEd by name, so the same
    concept defined in multiple regulations is represented as one shared
    Concept node — a useful retrieval hub.
    """
    concept_count = 0
    edge_count = 0
    for article in articles:
        defines = article.get("defines", [])
        if not defines:
            continue
        article_id = _article_node_id(article["regulation_id"], article["article_number"])
        for term in defines:
            session.run(
                "MERGE (c:Concept {name: $name})",
                name=term,
            )
            session.run(
                """
                MATCH (a:Article {id: $aid}), (c:Concept {name: $name})
                MERGE (a)-[:DEFINES]->(c)
                """,
                aid=article_id,
                name=term,
            )
            concept_count += 1
            edge_count += 1

    logger.info("Created/merged %d DEFINES edges (target Concepts).", edge_count)


if __name__ == "__main__":
    build_graph()
