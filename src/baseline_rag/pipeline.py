"""
pipeline.py — End-to-end Baseline RAG pipeline.

Vector-only retrieval (no graph expansion) + identical generator/prompt to
GraphRAGPipeline. The query() return shape mirrors GraphRAGPipeline so both
systems are drop-in interchangeable in the evaluation harness.

Usage:
    from src.baseline_rag.pipeline import BaselineRAGPipeline
    pipeline = BaselineRAGPipeline()
    result = pipeline.query("Apa saja syarat penyaluran DBH Sawit?")
"""
import logging
from typing import Any

from src import llm_client
from src.baseline_rag.retriever import retrieve
from src.config import TOP_K_VECTOR
from src.generation import SYSTEM_PROMPT, build_prompt, format_context

logger = logging.getLogger(__name__)


class BaselineRAGPipeline:
    def __init__(self, top_k: int = TOP_K_VECTOR):
        self.top_k = top_k

    def query(self, question: str) -> dict[str, Any]:
        """
        Returns:
            {
                "question": str,
                "answer": str,
                "context": list[dict],   # retrieved articles
            }
        """
        logger.info("BaselineRAG query: %s", question)

        context_articles = retrieve(question, top_k=self.top_k)
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
