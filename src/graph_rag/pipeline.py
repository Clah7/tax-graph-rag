"""
pipeline.py — End-to-end GraphRAG pipeline.

Two-stage retrieval (vector + graph expansion) + identical generator/prompt to
BaselineRAGPipeline. The query() return shape mirrors BaselineRAGPipeline so
both systems are drop-in interchangeable in the evaluation harness.

Usage:
    from src.graph_rag.pipeline import GraphRAGPipeline
    pipeline = GraphRAGPipeline()
    result = pipeline.query("Apa saja syarat penyaluran DBH Sawit?")
"""
import logging
from typing import Any

from src import llm_client
from src.config import GRAPH_HOP_DEPTH, GRAPH_RERANK_ALPHA, TOP_K_VECTOR
from src.generation import SYSTEM_PROMPT, build_prompt, format_context
from src.graph_rag.retriever import retrieve

logger = logging.getLogger(__name__)


class GraphRAGPipeline:
    def __init__(self, top_k: int = TOP_K_VECTOR, hop_depth: int = GRAPH_HOP_DEPTH,
                 alpha: float = GRAPH_RERANK_ALPHA):
        self.top_k = top_k
        self.hop_depth = hop_depth
        self.alpha = alpha

    def query(self, question: str) -> dict[str, Any]:
        """
        Returns:
            {
                "question": str,
                "answer": str,
                "context": list[dict],   # vector seeds + graph-expanded articles
            }
        """
        logger.info("GraphRAG query: %s", question)

        context_articles = retrieve(question, top_k=self.top_k, hop_depth=self.hop_depth, alpha=self.alpha)
        logger.info("Retrieved %d context articles.", len(context_articles))

        context_text = format_context(context_articles)
        prompt = build_prompt(question, context_text)

        answer = llm_client.generate(prompt, system=SYSTEM_PROMPT)
        logger.info("Generated answer (%d chars).", len(answer))

        return {
            "question": question,
            "answer": answer,
            "context": context_articles,
        }
