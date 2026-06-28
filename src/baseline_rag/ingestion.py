"""
ingestion.py — Embed parsed articles and store them in ChromaDB.

Pipeline:
  data/processed/articles.json
      └─ Ollama (qwen3-embedding:0.6b, 1024-dim, cosine)
          └─ ChromaDB PersistentClient → data/chroma_db/
                collection: "tax_articles"
"""
import json
import logging
import time
from typing import Any

import chromadb
import requests

from src.corpus import load_articles

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ARTICLES_JSON: str = "data/processed/articles.json"
CHROMA_DIR: str = "data/chroma_db"
COLLECTION_NAME: str = "tax_articles"

OLLAMA_URL: str = "http://localhost:11434/api/embed"
EMBED_MODEL: str = "qwen3-embedding:0.6b"
EMBED_DIM: int = 1024

# How many articles to embed in a single Ollama request.
# qwen3-embedding:0.6b handles batches well; keep it modest to avoid OOM.
BATCH_SIZE: int = 16

# Cap embed input length. qwen3-embedding:0.6b rejects inputs past its ~2048
# token limit with HTTP 400. Token density varies (dense OCR/numeric text hits
# the limit at fewer chars than prose), and the corpus contains mis-parsed
# mega-blob "articles" (up to ~9.9 MB), so no single char cap is universally
# safe. MAX_EMBED_CHARS is the initial cap most inputs pass at; on a 400 we
# progressively shrink only the offending text down to EMBED_MIN_CHARS. Only the
# embedding INPUT is truncated; the full text is still stored as the Chroma
# document / :Article.text.
MAX_EMBED_CHARS: int = 6000
EMBED_MIN_CHARS: int = 256


def _embed_request(texts: list[str]) -> list[list[float]]:
    """One Ollama /api/embed call; returns one 1024-dim vector per input."""
    resp = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    resp.raise_for_status()
    embeddings: list[list[float]] = resp.json()["embeddings"]
    if len(embeddings) != len(texts):
        raise ValueError(
            f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs."
        )
    return embeddings


def _is_400(exc: requests.exceptions.HTTPError) -> bool:
    return exc.response is not None and exc.response.status_code == 400


def _embed_one_with_shrink(text: str) -> list[float]:
    """Embed a single text, halving its length on each 400 until it fits."""
    n = min(len(text), MAX_EMBED_CHARS) or 1
    while True:
        try:
            return _embed_request([text[:n]])[0]
        except requests.exceptions.HTTPError as exc:
            if _is_400(exc) and n > EMBED_MIN_CHARS:
                n = max(EMBED_MIN_CHARS, n // 2)
                logger.warning("embed 400; retrying a single text at %d chars.", n)
                continue
            raise


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch via Ollama. Fast path sends the whole batch (each input capped
    at MAX_EMBED_CHARS). If the model rejects the batch with HTTP 400 (a text too
    dense/long even after the cap), fall back to per-text embedding that shrinks
    only the offending input — so one pathological article can't fail the batch.
    """
    capped = [t[:MAX_EMBED_CHARS] for t in texts]
    try:
        return _embed_request(capped)
    except requests.exceptions.HTTPError as exc:
        if not _is_400(exc):
            raise
        logger.warning(
            "Batch embed got HTTP 400; falling back to per-text shrink for %d texts.",
            len(texts),
        )
        return [_embed_one_with_shrink(t) for t in texts]


# ---------------------------------------------------------------------------
# ChromaDB helpers
# ---------------------------------------------------------------------------
def _get_collection(chroma_dir: str, collection_name: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def _make_doc_id(regulation_id: str, article_number: str) -> str:
    """
    Stable, unique document ID for a Pasal.
    Example: "PMK 10 TAHUN 2026::5"
    """
    return f"{regulation_id}::{article_number}"


def _article_to_metadata(article: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten the article dict into ChromaDB-compatible metadata.
    ChromaDB only accepts str/int/float/bool values, so references
    (a list) are serialised as a JSON string.
    """
    return {
        "regulation_id": article["regulation_id"],
        "article_number": article["article_number"],
        "references": json.dumps(article.get("references", []), ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def ingest(
    articles_path: str = ARTICLES_JSON,
    chroma_dir: str = CHROMA_DIR,
    collection_name: str = COLLECTION_NAME,
    batch_size: int = BATCH_SIZE,
) -> None:
    # 1. Load + deduplicate articles (shared rule — see src/corpus.py / ADR 0006)
    articles = load_articles(articles_path)

    # 2. Open / create ChromaDB collection
    collection = _get_collection(chroma_dir, collection_name)
    existing_count = collection.count()
    logger.info(
        "Collection '%s' opened — %d documents already present.",
        collection_name, existing_count,
    )

    # 3. Skip articles whose IDs are already in the collection
    #    Query in small batches to avoid ChromaDB limits
    all_ids = [_make_doc_id(a["regulation_id"], a["article_number"]) for a in articles]
    existing_ids: set[str] = set()
    if existing_count > 0:
        CHECK_BATCH = 500
        for i in range(0, len(all_ids), CHECK_BATCH):
            chunk = all_ids[i: i + CHECK_BATCH]
            result = collection.get(ids=chunk, include=[])
            existing_ids.update(result["ids"])

    pending = [a for a, doc_id in zip(articles, all_ids) if doc_id not in existing_ids]
    if not pending:
        logger.info("All articles already ingested — nothing to do.")
        return
    logger.info("%d articles to embed and ingest (%d already present).",
                len(pending), len(existing_ids))

    # 4. Embed in batches and upsert into ChromaDB
    total_ingested = 0
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start: batch_start + batch_size]
        texts = [a["content"] for a in batch]
        ids = [_make_doc_id(a["regulation_id"], a["article_number"]) for a in batch]
        metadatas = [_article_to_metadata(a) for a in batch]

        logger.info(
            "Embedding batch %d–%d / %d …",
            batch_start + 1, batch_start + len(batch), len(pending),
        )
        t0 = time.perf_counter()
        try:
            embeddings = _embed_batch(texts)
        except requests.exceptions.RequestException as exc:
            logger.error("Ollama request failed for batch starting at %d: %s", batch_start, exc)
            raise

        elapsed = time.perf_counter() - t0
        logger.info("  Embedded in %.2fs — upserting to ChromaDB …", elapsed)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        total_ingested += len(batch)

    logger.info(
        "Ingestion complete. %d new articles stored in '%s' (collection '%s').",
        total_ingested, chroma_dir, collection_name,
    )
    logger.info("Collection total: %d documents.", collection.count())


if __name__ == "__main__":
    ingest()
