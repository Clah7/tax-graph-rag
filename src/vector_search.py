"""
vector_search.py — Shared ChromaDB vector retrieval.

BaselineRAGPipeline and GraphRAGPipeline both call this so that the Stage 1
vector step (embedding model, collection, top-k, scoring) is bit-for-bit
identical across systems. Any measured difference between the two pipelines
must therefore come from the graph expansion, not from retrieval drift.

Returned article dict shape:
    id              str   "<regulation_id>::<article_number>"
    regulation_id   str
    article_number  str
    text            str
    references      list  (intra-regulation references stored in Chroma)
    score           float cosine similarity in [-1, 1]; higher is better
    source          str   always "vector"
"""
import json
from typing import Any

import chromadb

from src import llm_client
from src.config import CHROMA_COLLECTION, CHROMA_DIR


def vector_search(query: str, top_k: int) -> list[dict[str, Any]]:
    query_embedding = llm_client.embed([query])[0]

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(CHROMA_COLLECTION)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )


    articles: list[dict[str, Any]] = []
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
            "score": 1.0 - dist,
            "source": "vector",
        })
    return articles


def fetch_embeddings(ids: list[str]) -> dict[str, list[float]]:
    """Return stored (query-space) embeddings for the given article ids.

    Used by GraphRAG to score graph-expanded neighbors against the query in the
    exact same embedding space as the seeds — no re-embedding, no drift. Ids
    missing from the collection are simply absent from the result.
    """
    if not ids:
        return {}
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(CHROMA_COLLECTION)
    res = collection.get(ids=ids, include=["embeddings"])
    return {i: emb for i, emb in zip(res["ids"], res["embeddings"])}
