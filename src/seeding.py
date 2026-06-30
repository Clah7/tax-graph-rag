"""
seeding.py — Single dispatch point for the shared Stage-1 seed retrieval.

Both BaselineRAG and GraphRAG seed from here, so the (dense vs hybrid) choice is
made in exactly one place and stays identical across the two systems — any graph
advantage must come from the graph stage, not from seeding drift.

`config.USE_HYBRID_SEEDING` is read at call time (not import) so an ablation
driver can flip it in-process between runs.
"""
from typing import Any

import src.config as config
from src.hybrid_search import hybrid_search
from src.vector_search import vector_search


def seed_search(query: str, top_k: int) -> list[dict[str, Any]]:
    if config.USE_HYBRID_SEEDING:
        return hybrid_search(query, top_k)
    return vector_search(query, top_k)
