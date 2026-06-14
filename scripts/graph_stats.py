"""
graph_stats.py — Summary statistics of the Neo4j knowledge graph.

Run:
    python -m scripts.graph_stats

Prints node counts, edge counts, orphan articles, top-degree articles, and
the most-connected concepts. Use it as a sanity check after ingestion and
as a sourcing for thesis figures.
"""
from neo4j import GraphDatabase

from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER


COUNT_QUERIES: list[tuple[str, str]] = [
    ("Regulations",         "MATCH (r:Regulation)         RETURN count(r) AS c"),
    ("Articles",            "MATCH (a:Article)            RETURN count(a) AS c"),
    ("Concepts",            "MATCH (c:Concept)            RETURN count(c) AS c"),
    ("BELONGS_TO edges",    "MATCH ()-[r:BELONGS_TO]->()  RETURN count(r) AS c"),
    ("REFERENCES edges",    "MATCH ()-[r:REFERENCES]->()  RETURN count(r) AS c"),
    ("AMENDS edges",        "MATCH ()-[r:AMENDS]->()      RETURN count(r) AS c"),
    ("DEFINES edges",       "MATCH ()-[r:DEFINES]->()     RETURN count(r) AS c"),
]


HEALTH_QUERIES: list[tuple[str, str]] = [
    (
        "Orphan articles (no REFERENCES & no DEFINES)",
        "MATCH (a:Article) "
        "WHERE NOT (a)-[:REFERENCES]-() AND NOT (a)-[:DEFINES]->() "
        "RETURN count(a) AS c",
    ),
    (
        "Articles defining >=1 concept",
        "MATCH (a:Article)-[:DEFINES]->() RETURN count(DISTINCT a) AS c",
    ),
    (
        "Regulation stubs (no articles ingested but referenced via AMENDS)",
        "MATCH (r:Regulation) WHERE NOT (r)<-[:BELONGS_TO]-() RETURN count(r) AS c",
    ),
]


TOP_QUERIES: list[tuple[str, str]] = [
    (
        "Top 10 most-referenced articles (incoming REFERENCES)",
        "MATCH (a:Article)<-[:REFERENCES]-() "
        "RETURN a.id AS id, count(*) AS deg "
        "ORDER BY deg DESC LIMIT 10",
    ),
    (
        "Top 10 most-defined concepts (incoming DEFINES)",
        "MATCH (c:Concept)<-[:DEFINES]-() "
        "RETURN c.name AS name, count(*) AS deg "
        "ORDER BY deg DESC LIMIT 10",
    ),
    (
        "Top 10 most-amended regulations (incoming AMENDS)",
        "MATCH (r:Regulation)<-[:AMENDS]-() "
        "RETURN r.id AS id, count(*) AS deg "
        "ORDER BY deg DESC LIMIT 10",
    ),
]


def _run_scalar(session, cypher: str) -> int:
    rec = session.run(cypher).single()
    return int(rec["c"]) if rec else 0


def _print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            _print_section("Node & edge counts")
            for label, cypher in COUNT_QUERIES:
                print(f"  {label:<22s} {_run_scalar(session, cypher):>10,d}")

            _print_section("Health checks")
            for label, cypher in HEALTH_QUERIES:
                print(f"  {label:<60s} {_run_scalar(session, cypher):>8,d}")

            for label, cypher in TOP_QUERIES:
                _print_section(label)
                for rec in session.run(cypher):
                    key = rec.get("id") or rec.get("name") or "?"
                    print(f"  {rec['deg']:>5d}  {key}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
