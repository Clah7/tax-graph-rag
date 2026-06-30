"""
hybrid_search.py — Hybrid lexical+dense seeding, drop-in for vector_search.

Diagnosis (2026-07-01): the 0.6b embedder recalls the right article into a deep
candidate pool but ranks it below the top-5 cutoff (41/44 gold IDs sit within the
dense top-200, many at rank 30-170). Lexical signal anchors the cited terms
("Pajak Hotel", "Bea Perolehan Hak", regulation names) the dense model smears.

Pipeline (no global BM25 index — only the pool is scored):
    1. Dense query for the top-HYBRID_POOL candidates (ids, text, cosine).
    2. BM25 re-rank of those pool documents against the query.
    3. Reciprocal Rank Fusion of the dense and lexical orderings (HYBRID_RRF_K).
    4. Return the fused top-k.

Returned article dict shape mirrors src.vector_search.vector_search, plus:
    score        float  dense cosine similarity (carried for graph-boost math)
    fused_score  float  RRF score that determined the ordering
    source       str    "hybrid"

Measured retrieval-only on the held-out test split (vs dense-only top-5):
    recall@5 .469->.521, hit@5 .625->.750, mrr .424->.547.
"""
import json
import math
import re
from collections import Counter
from typing import Any

import chromadb

from src import llm_client
from src.config import CHROMA_COLLECTION, CHROMA_DIR, HYBRID_POOL, HYBRID_RRF_K

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    # Keep digits: article numbers ("Pasal 17") and rates ("0,5%") carry signal.
    return _TOKEN.findall(text.lower())


def _bm25_order(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[int]:
    """Return pool indices ordered by BM25 score (desc). idf is over the pool."""
    toks = [_tokenize(d) for d in docs]
    n = len(toks)
    if n == 0:
        return []
    avg_len = sum(len(t) for t in toks) / n
    df: Counter = Counter()
    for t in toks:
        df.update(set(t))

    q_terms = set(_tokenize(query))
    scores = []
    for t in toks:
        tf = Counter(t)
        s = 0.0
        for w in q_terms:
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg_len))
        scores.append(s)
    return sorted(range(n), key=lambda i: -scores[i])


def hybrid_search(query: str, top_k: int, pool: int = HYBRID_POOL) -> list[dict[str, Any]]:
    query_embedding = llm_client.embed([query])[0]

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(CHROMA_COLLECTION)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=pool,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]
    ids = [f"{m['regulation_id']}::{m['article_number']}" for m in metas]

    # Rank maps for fusion. Dense order is the pool order as returned.
    dense_rank = {i: r for r, i in enumerate(range(len(ids)))}
    lex_rank = {idx: r for r, idx in enumerate(_bm25_order(query, docs))}

    def rrf(i: int) -> float:
        return 1.0 / (HYBRID_RRF_K + dense_rank[i]) + 1.0 / (HYBRID_RRF_K + lex_rank.get(i, len(ids)))

    order = sorted(range(len(ids)), key=lambda i: (-rrf(i), ids[i]))

    articles: list[dict[str, Any]] = []
    for i in order[:top_k]:
        articles.append({
            "id": ids[i],
            "regulation_id": metas[i]["regulation_id"],
            "article_number": metas[i]["article_number"],
            "text": docs[i],
            "references": json.loads(metas[i].get("references", "[]")),
            "score": 1.0 - dists[i],   # dense cosine, for downstream graph-boost
            "fused_score": rrf(i),
            "source": "hybrid",
        })
    return articles
