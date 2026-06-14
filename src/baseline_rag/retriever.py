"""
retriever.py — Single-stage vector retrieval for Baseline RAG.

This is the no-graph baseline: embed the query and return the top-K
semantically similar articles from ChromaDB. Any GraphRAG advantage in the
comparative evaluation must come from beating this.
"""
import logging
from typing import Any

from src.config import TOP_K_VECTOR
from src.vector_search import vector_search

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = TOP_K_VECTOR) -> list[dict[str, Any]]:
    articles = vector_search(query, top_k)
    logger.info("Vector search returned %d articles.", len(articles))
    return articles
