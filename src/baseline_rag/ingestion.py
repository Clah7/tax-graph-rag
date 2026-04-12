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


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def _embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Call the Ollama /api/embed endpoint for a batch of texts.
    Returns a list of 1024-dimensional float vectors, one per input text.
    """
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
    # 1. Load articles
    with open(articles_path, encoding="utf-8") as fh:
        articles: list[dict[str, Any]] = json.load(fh)
    logger.info("Loaded %d articles from '%s'.", len(articles), articles_path)

    # 2. Open / create ChromaDB collection
    collection = _get_collection(chroma_dir, collection_name)
    existing_count = collection.count()
    logger.info(
        "Collection '%s' opened — %d documents already present.",
        collection_name, existing_count,
    )

    # 3. Skip articles whose IDs are already in the collection
    all_ids = [_make_doc_id(a["regulation_id"], a["article_number"]) for a in articles]
    if existing_count > 0:
        existing = collection.get(ids=all_ids, include=[])
        existing_ids: set[str] = set(existing["ids"])
    else:
        existing_ids = set()

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
