"""
ir_metrics.py — Classical retrieval metrics on `gold_article_ids`.

These are the primary defensible signal for the thesis: "did the system
retrieve the correct Pasal?" — measured against hand-labelled gold IDs, with
no LLM in the loop.

All functions operate on a single (gold, retrieved) pair so the caller can
aggregate per slice (e.g. by hop_type) without re-traversing the result list.
"""
from __future__ import annotations

from typing import Iterable


def recall_at_k(gold: Iterable[str], retrieved: list[str], k: int) -> float:
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    top = set(retrieved[:k])
    return len(top & gold_set) / len(gold_set)


def precision_at_k(gold: Iterable[str], retrieved: list[str], k: int) -> float:
    if k <= 0:
        return 0.0
    gold_set = set(gold)
    top = retrieved[:k]
    if not top:
        return 0.0
    hits = sum(1 for r in top if r in gold_set)
    return hits / min(k, len(top))


def mrr(gold: Iterable[str], retrieved: list[str]) -> float:
    gold_set = set(gold)
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in gold_set:
            return 1.0 / rank
    return 0.0


def hit_at_k(gold: Iterable[str], retrieved: list[str], k: int) -> float:
    """1.0 if any gold ID appears in retrieved[:k], else 0.0."""
    return 1.0 if set(retrieved[:k]) & set(gold) else 0.0


def score_row(gold: list[str], retrieved: list[str], k_values: tuple[int, ...] = (1, 3, 5, 10, 20)) -> dict[str, float]:
    """Compute all IR metrics for one (gold, retrieved) pair."""
    out: dict[str, float] = {"mrr": mrr(gold, retrieved)}
    for k in k_values:
        out[f"recall@{k}"]    = recall_at_k(gold, retrieved, k)
        out[f"precision@{k}"] = precision_at_k(gold, retrieved, k)
        out[f"hit@{k}"]       = hit_at_k(gold, retrieved, k)
    return out
