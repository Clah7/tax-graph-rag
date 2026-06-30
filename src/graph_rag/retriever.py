"""
retriever.py — Two-stage GraphRAG retrieval with strict-parity re-ranking.

Stage 1 — Vector search (ChromaDB):
    Embed the query and find the top-K semantically similar articles.
    Delegated to src.vector_search so the step is bit-for-bit identical
    to BaselineRAG.

Stage 2 — Graph expansion (Neo4j):
    From the seeds, follow REFERENCES edges up to GRAPH_HOP_DEPTH hops and
    collect reached articles, tracking for each one: which seeds reach it, the
    shortest hop per seed, and the article's REFERENCES degree.

Stage 3 — Strict-parity re-rank:
    Score every candidate (seeds + reached neighbors) and truncate to
    GRAPH_CONTEXT_BUDGET (== TOP_K_VECTOR). Baseline feeds the same budget, so a
    linked neighbor can only enter context by out-scoring a weak seed.

        score(x) = query_sim(x) + alpha * boost(x)

        boost(x) = ( Σ over seeds s reaching x of  sim(s) / hop(s, x) )
                   / ( 1 + log(1 + degree(x)) )

    Design choices, both diagnosed from the v25 regression (alpha=0.5, naive
    boost) where amendment-law hubs displaced gold seeds:
      * SYMMETRIC — seeds are scored with the same formula (a seed reached from
        other seeds earns boost too), so a relevant gold seed is not unfairly
        displaced by a neighbour that merely carries a boost term.
      * DEGREE-DAMPED — dividing by 1+log(1+degree) means high-degree hub nodes
        (which reference everything, so a link to them means little) earn far
        less boost per link than a low-degree, specifically-referenced article.
      * alpha=0 reproduces baseline exactly. TUNE ALPHA ON THE DEV SPLIT ONLY
        (scripts.tune_alpha); never on the held-out test split.

`gather()` does all the I/O (embed, vector search, graph, neighbor embeddings)
and is independent of alpha; `rerank()` is pure-Python and alpha-dependent, so
the tuner can sweep alpha without re-querying.
"""
import logging
import math
from typing import Any

from neo4j import GraphDatabase

from src import llm_client
from src.config import (
    GRAPH_CONTEXT_BUDGET,
    GRAPH_HOP_DEPTH,
    GRAPH_RERANK_ALPHA,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    TOP_K_VECTOR,
)
from src.vector_search import fetch_embeddings, vector_search

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    top_k: int = TOP_K_VECTOR,
    hop_depth: int = GRAPH_HOP_DEPTH,
    alpha: float = GRAPH_RERANK_ALPHA,
    budget: int = GRAPH_CONTEXT_BUDGET,
) -> list[dict[str, Any]]:
    """Returns the top-`budget` re-ranked article dicts for the generator."""
    bundle = gather(query, top_k=top_k, hop_depth=hop_depth)
    return rerank(bundle, alpha=alpha, budget=budget)


# ---------------------------------------------------------------------------
# Stage 1+2: gather candidates (all alpha-independent I/O)
# ---------------------------------------------------------------------------
def gather(query: str, top_k: int = TOP_K_VECTOR, hop_depth: int = GRAPH_HOP_DEPTH) -> dict[str, Any]:
    """Vector seeds + graph-reached neighbors + their query-space embeddings.

    Cacheable per query: nothing here depends on the re-rank alpha.
    """
    query_embedding = llm_client.embed([query])[0]

    seed_articles = vector_search(query, top_k)
    seed_ids = [a["id"] for a in seed_articles]
    seed_score = {a["id"]: a["score"] for a in seed_articles}
    logger.info("Vector search returned %d seed articles: %s", len(seed_ids), seed_ids)

    reached = _graph_expand(seed_ids, hop_depth)
    logger.info("Graph expansion reached %d articles.", len(reached))

    # Query similarity for non-seed reached articles, in the seeds' embedding space.
    neighbor_ids = [i for i in reached if i not in seed_score]
    neighbor_emb = fetch_embeddings(neighbor_ids)

    return {
        "query_embedding": query_embedding,
        "seed_articles": seed_articles,
        "seed_score": seed_score,
        "reached": reached,
        "neighbor_emb": neighbor_emb,
    }


def _graph_expand(seed_ids: list[str], hop_depth: int) -> dict[str, dict[str, Any]]:
    """Map id -> {regulation_id, article_number, text, degree, via}.

    Reached targets include other seeds (self excluded), so seed boost is
    symmetric. `via` is the list of {seed, hop} entries that reach the target;
    `degree` is the target's REFERENCES degree (for hub damping).
    """
    if not seed_ids:
        return {}

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            records = session.run(
                f"""
                UNWIND $seed_ids AS seed
                MATCH (src:Article {{id: seed}})
                MATCH path = (src)-[:REFERENCES*1..{hop_depth}]-(t:Article)
                WHERE t.id <> seed
                WITH t, seed, min(length(path)) AS hop
                RETURN
                    t.id             AS id,
                    t.regulation_id  AS regulation_id,
                    t.article_number AS article_number,
                    t.text           AS text,
                    COUNT {{ (t)-[:REFERENCES]-(:Article) }} AS degree,
                    collect({{seed: seed, hop: hop}}) AS via
                """,
                seed_ids=seed_ids,
            )
            reached: dict[str, dict[str, Any]] = {}
            for r in records:
                reached[r["id"]] = {
                    "regulation_id": r["regulation_id"],
                    "article_number": r["article_number"],
                    "text": r["text"],
                    "degree": r["degree"],
                    "via": r["via"],
                }
    finally:
        driver.close()

    return reached


# ---------------------------------------------------------------------------
# Stage 3: strict-parity re-rank (pure-python, alpha-dependent)
# ---------------------------------------------------------------------------
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _boost(article_id: str, reached: dict[str, dict[str, Any]], seed_score: dict[str, float]) -> float:
    info = reached.get(article_id)
    if not info:
        return 0.0
    raw = sum(
        seed_score.get(v["seed"], 0.0) / max(v["hop"], 1)
        for v in info["via"]
        if v["seed"] != article_id
    )
    return raw / (1.0 + math.log(1 + info["degree"]))


def rerank(bundle: dict[str, Any], alpha: float = GRAPH_RERANK_ALPHA, budget: int = GRAPH_CONTEXT_BUDGET) -> list[dict[str, Any]]:
    seed_score = bundle["seed_score"]
    reached = bundle["reached"]
    neighbor_emb = bundle["neighbor_emb"]
    query_embedding = bundle["query_embedding"]
    seed_ids = set(seed_score)

    candidates: list[dict[str, Any]] = []

    for seed in bundle["seed_articles"]:
        sim = seed["score"]
        candidates.append({
            **seed,
            "score": sim + alpha * _boost(seed["id"], reached, seed_score),
        })

    for nid, info in reached.items():
        if nid in seed_ids:
            continue
        emb = neighbor_emb.get(nid)
        sim = _cosine(query_embedding, emb) if emb is not None else 0.0
        candidates.append({
            "id": nid,
            "regulation_id": info["regulation_id"],
            "article_number": info["article_number"],
            "text": info["text"],
            "references": [],
            "source": "graph",
            "score": sim + alpha * _boost(nid, reached, seed_score),
        })

    # Stable, deterministic order: score desc, id asc as tie-break.
    candidates.sort(key=lambda a: (-a["score"], a["id"]))

    ranked = candidates[:budget]
    logger.info(
        "Re-ranked %d candidates -> top %d (alpha=%.3g, %d graph-promoted).",
        len(candidates), len(ranked), alpha,
        sum(1 for a in ranked if a["source"] == "graph"),
    )
    return ranked
