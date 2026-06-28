"""
migrate_dedup_text.py — Apply the ADR 0006 dedup fix to the LIVE stores without
a full re-ingest.

The shared loader (`src/corpus.py`) now picks the batang tubuh over penjelasan /
lampiran fragments, but ChromaDB and Neo4j were built under the old "keep last"
rule and still hold the wrong text for ~18k articles. This script rewrites only
the articles whose canonical text changed.

Scope and cost:
  * ChromaDB — documents AND embeddings must change (the stale embedding was
    computed from the wrong text). Only changed docs are re-embedded: ~18k of
    118,966 (~45 min) instead of the full ~5h baseline rebuild. This is the
    reason to migrate rather than re-ingest.
  * Neo4j — sets :Article.text for changed IDs (cheap, no embedding). This fixes
    the *context text* graph RAG assembles, but does NOT rebuild REFERENCES /
    DEFINES edges. The corrected batang tubuh usually has MORE references than
    the penjelasan it replaces, so for edge-correct results rebuild the graph:
        python -m scripts.reset_stores --yes   # (wipes both — or wipe Neo4j only)
        python main.py ingest-graph            # ~40 min
    Use --skip-neo4j if you intend to do the full graph rebuild instead.

Safe by default: runs a DRY RUN (reports counts, writes nothing). Pass --apply to
commit. Idempotent — a second run finds 0 differences.

    python -m scripts.migrate_dedup_text                 # dry run
    python -m scripts.migrate_dedup_text --apply         # migrate both stores
    python -m scripts.migrate_dedup_text --apply --skip-neo4j
"""
from __future__ import annotations

import argparse
import logging

from neo4j import GraphDatabase

from src.baseline_rag.ingestion import (
    COLLECTION_NAME,
    CHROMA_DIR,
    _article_to_metadata,
    _embed_batch,
    _get_collection,
    _make_doc_id,
)
from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from src.corpus import article_text, load_articles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_dedup_text")

GET_BATCH = 500       # ids per Chroma .get when diffing
EMBED_BATCH = 16      # matches baseline ingestion batch size
NEO4J_BATCH = 1000


def _find_changed(collection, articles: list[dict]) -> tuple[list[dict], int]:
    """Return (articles whose stored Chroma doc differs / is missing, n_missing)."""
    by_id = {_make_doc_id(a["regulation_id"], a["article_number"]): a for a in articles}
    ids = list(by_id)
    changed: list[dict] = []
    missing = 0
    for i in range(0, len(ids), GET_BATCH):
        chunk = ids[i: i + GET_BATCH]
        got = collection.get(ids=chunk, include=["documents"])
        stored = dict(zip(got["ids"], got["documents"]))
        for aid in chunk:
            want = by_id[aid]["content"]
            have = stored.get(aid)
            if have is None:
                missing += 1
                changed.append(by_id[aid])
            elif have != want:
                changed.append(by_id[aid])
    return changed, missing


def _migrate_chroma(articles: list[dict], apply: bool) -> int:
    collection = _get_collection(CHROMA_DIR, COLLECTION_NAME)
    logger.info("Diffing %d canonical articles against ChromaDB …", len(articles))
    changed, missing = _find_changed(collection, articles)
    logger.info("ChromaDB: %d docs differ (incl. %d missing) of %d.",
                len(changed), missing, len(articles))
    if not apply or not changed:
        return len(changed)

    for start in range(0, len(changed), EMBED_BATCH):
        batch = changed[start: start + EMBED_BATCH]
        texts = [a["content"] for a in batch]
        ids = [_make_doc_id(a["regulation_id"], a["article_number"]) for a in batch]
        metas = [_article_to_metadata(a) for a in batch]
        embeddings = _embed_batch(texts)
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
        logger.info("  re-embedded %d / %d", min(start + len(batch), len(changed)), len(changed))
    logger.info("ChromaDB migration done: %d docs updated.", len(changed))
    return len(changed)


def _migrate_neo4j(articles: list[dict], apply: bool) -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    rows = [{"id": _make_doc_id(a["regulation_id"], a["article_number"]),
             "text": a["content"]} for a in articles]
    n_diff = 0
    try:
        with driver.session() as session:
            # count how many differ first (dry-run friendly)
            for i in range(0, len(rows), NEO4J_BATCH):
                chunk = rows[i: i + NEO4J_BATCH]
                rec = session.run(
                    "UNWIND $rows AS r MATCH (a:Article {id: r.id}) "
                    "WHERE a.text <> r.text RETURN count(a) AS c", rows=chunk
                ).single()
                n_diff += int(rec["c"]) if rec else 0
            logger.info("Neo4j: %d :Article.text values differ.", n_diff)
            if apply and n_diff:
                for i in range(0, len(rows), NEO4J_BATCH):
                    chunk = rows[i: i + NEO4J_BATCH]
                    session.run(
                        "UNWIND $rows AS r MATCH (a:Article {id: r.id}) "
                        "SET a.text = r.text", rows=chunk
                    )
                logger.info("Neo4j text migration done. NOTE: REFERENCES/DEFINES "
                            "edges NOT rebuilt — run `ingest-graph` for edge correctness.")
    finally:
        driver.close()
    return n_diff


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.migrate_dedup_text")
    ap.add_argument("--apply", action="store_true", help="Commit changes (default: dry run).")
    ap.add_argument("--skip-neo4j", action="store_true",
                    help="Migrate ChromaDB only (use when rebuilding the graph instead).")
    args = ap.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN (no writes)"
    logger.info("Mode: %s", mode)

    articles = load_articles()
    chroma_changed = _migrate_chroma(articles, args.apply)
    neo4j_changed = 0 if args.skip_neo4j else _migrate_neo4j(articles, args.apply)

    logger.info("Summary — ChromaDB: %d, Neo4j: %s",
                chroma_changed, "skipped" if args.skip_neo4j else neo4j_changed)
    if not args.apply:
        logger.info("Dry run only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
