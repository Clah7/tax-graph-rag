"""
validate_ground_truth.py — Resolve every gold article ID in the eval set
against both stores (ChromaDB + Neo4j).

Run:
    python -m scripts.validate_ground_truth

Why: a `gold_article_id` that doesn't match a real `:Article` / Chroma doc
silently scores 0 recall and masquerades as a retrieval failure. Catch these
before scaling the ground-truth set or running the harness. The OCR `O`->`0`
issue (capital O where digit 0 belongs) is the usual culprit, so IDs that look
suspicious are flagged separately.

A second failure mode (ADR 0006): a gold ID that *resolves* but points at
elucidation ("Cukup jelas.") or a trivial fragment instead of the operative
batang tubuh — the omnibus-collision residue dedup can't fix by selection. Such
IDs score recall fine yet make `gold_answer` unverifiable, so the resolved
Chroma text is checked against the same usable-body rule the dedup uses.

Exit code: 0 if every gold ID resolves in BOTH stores AND resolves to usable
batang-tubuh text, else 1.
"""
import re
import sys

import chromadb
from neo4j import GraphDatabase

from src.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
)
from src.corpus import _is_usable_body
from src.evaluation.dataset import load_dataset

# Capital O sitting next to a digit inside the article-number tail — the
# signature of the known OCR corruption (e.g. "...::1O" or "...::2O1").
_OCR_SUSPECT = re.compile(r"::[^:]*[0-9]?O[0-9]?")


def _chroma_docs(ids: list[str]) -> dict[str, str]:
    """Map each present gold ID to its stored Chroma document text."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(CHROMA_COLLECTION)
    got = collection.get(ids=ids, include=["documents"])
    return dict(zip(got["ids"], got["documents"]))


def _neo4j_present(ids: list[str]) -> set[str]:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            rec = session.run(
                "MATCH (a:Article) WHERE a.id IN $ids RETURN collect(a.id) AS ids",
                ids=ids,
            ).single()
            return set(rec["ids"]) if rec else set()
    finally:
        driver.close()


def main() -> int:
    items = load_dataset()
    all_ids = sorted({gid for it in items for gid in it.gold_article_ids})
    if not all_ids:
        print("No gold IDs found in eval set.")
        return 1

    print(f"Validating {len(all_ids)} unique gold IDs "
          f"across {len(items)} questions...\n")

    chroma_docs = _chroma_docs(all_ids)
    in_chroma = set(chroma_docs)
    in_neo4j = _neo4j_present(all_ids)

    bad_questions = 0
    trivial_ids = 0
    for it in items:
        problems: list[str] = []
        for gid in it.gold_article_ids:
            missing = []
            if gid not in in_chroma:
                missing.append("Chroma")
            if gid not in in_neo4j:
                missing.append("Neo4j")
            flag = "  <-- OCR O/0?" if _OCR_SUSPECT.search(gid) else ""
            if missing:
                problems.append(f"    MISSING in {', '.join(missing):<13s} {gid}{flag}")
                continue
            # Resolves — but to usable batang tubuh, or to penjelasan/fragment?
            if not _is_usable_body((chroma_docs.get(gid) or "").strip()):
                trivial_ids += 1
                snippet = (chroma_docs.get(gid) or "").strip()[:50].replace("\n", " ")
                problems.append(
                    f"    PENJELASAN/TRIVIAL text     {gid}  ->  {snippet!r}"
                )
            elif flag:
                problems.append(f"    ok but suspicious id        {gid}{flag}")
        if problems:
            bad_questions += 1
            print(f"[{it.id}] {it.question[:60]}")
            print("\n".join(problems))
            print()

    total = len(all_ids)
    id_set = set(all_ids)
    print("=" * 70)
    print(f"  resolved in Chroma : {len(in_chroma & id_set)}/{total}")
    print(f"  resolved in Neo4j  : {len(in_neo4j & id_set)}/{total}")
    print(f"  penjelasan/trivial resolved text: {trivial_ids}/{total}")
    print(f"  questions with problems: {bad_questions}/{len(items)}")
    print("=" * 70)

    return 0 if bad_questions == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
