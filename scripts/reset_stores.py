"""
reset_stores.py — Wipe ChromaDB and Neo4j so they can be rebuilt from
data/processed/articles.json by the ingestion pipelines.

What it does:
  1. Removes the ChromaDB persistent directory (CHROMA_DIR).
  2. Connects to Neo4j and runs DETACH DELETE on every node, then drops
     the constraints created by graph_rag.ingestion (they're re-created
     on the next build_graph()).

Run:
    python -m scripts.reset_stores            # asks for confirmation
    python -m scripts.reset_stores --yes      # skip confirmation
    python -m scripts.reset_stores --chroma   # only ChromaDB
    python -m scripts.reset_stores --neo4j    # only Neo4j
"""
import argparse
import logging
import shutil
from pathlib import Path

from neo4j import GraphDatabase

from src.config import CHROMA_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CONSTRAINTS = ["article_id", "regulation_id", "concept_name"]


def wipe_chroma(chroma_dir: str) -> None:
    path = Path(chroma_dir)
    if not path.exists():
        logger.info("ChromaDB dir '%s' does not exist — nothing to wipe.", chroma_dir)
        return
    shutil.rmtree(path)
    logger.info("Removed ChromaDB dir '%s'.", chroma_dir)


def wipe_neo4j() -> None:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            # DETACH DELETE in batches to avoid heap blow-up on big graphs.
            while True:
                result = session.run(
                    "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(n) AS c"
                ).single()
                deleted = result["c"] if result else 0
                logger.info("Deleted %d nodes.", deleted)
                if deleted == 0:
                    break

            for name in CONSTRAINTS:
                session.run(f"DROP CONSTRAINT {name} IF EXISTS")
            logger.info("Dropped constraints: %s", ", ".join(CONSTRAINTS))
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    parser.add_argument("--chroma", action="store_true", help="only wipe ChromaDB")
    parser.add_argument("--neo4j", action="store_true", help="only wipe Neo4j")
    args = parser.parse_args()

    do_chroma = args.chroma or not args.neo4j
    do_neo4j = args.neo4j or not args.chroma

    targets = []
    if do_chroma:
        targets.append(f"ChromaDB ({CHROMA_DIR})")
    if do_neo4j:
        targets.append(f"Neo4j ({NEO4J_URI})")

    print("About to WIPE the following stores:")
    for t in targets:
        print(f"  - {t}")

    if not args.yes:
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    if do_chroma:
        wipe_chroma(CHROMA_DIR)
    if do_neo4j:
        wipe_neo4j()

    logger.info("Reset complete.")


if __name__ == "__main__":
    main()
