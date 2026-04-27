"""
pipeline.py — End-to-end GraphRAG pipeline.

Usage:
    from src.graph_rag.pipeline import GraphRAGPipeline
    pipeline = GraphRAGPipeline()
    answer = pipeline.query("Apa saja syarat penyaluran DBH Sawit?")
"""
import logging
from typing import Any

from src import llm_client
from src.graph_rag.retriever import retrieve

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Anda adalah asisten hukum pajak Indonesia yang ahli dalam peraturan perpajakan.
Jawablah pertanyaan pengguna berdasarkan konteks pasal-pasal peraturan yang diberikan.
Sebutkan nomor pasal dan peraturan yang relevan dalam jawaban Anda.
Jika informasi tidak tersedia dalam konteks, katakan bahwa informasi tersebut tidak ditemukan dalam peraturan yang ada."""


class GraphRAGPipeline:
    def __init__(self, top_k: int = 5, hop_depth: int = 2):
        self.top_k = top_k
        self.hop_depth = hop_depth

    def query(self, question: str) -> dict[str, Any]:
        """
        Returns:
            {
                "question": str,
                "answer": str,
                "context": list[dict],   # articles used
            }
        """
        logger.info("GraphRAG query: %s", question)

        context_articles = retrieve(question, top_k=self.top_k, hop_depth=self.hop_depth)
        logger.info("Retrieved %d context articles.", len(context_articles))

        context_text = _format_context(context_articles)
        prompt = _build_prompt(question, context_text)

        answer = llm_client.generate(prompt, system=_SYSTEM_PROMPT)
        logger.info("Generated answer (%d chars).", len(answer))

        return {
            "question": question,
            "answer": answer,
            "context": context_articles,
        }


def _format_context(articles: list[dict[str, Any]]) -> str:
    parts = []
    for article in articles:
        source_tag = f"[{article['source'].upper()}]"
        header = f"{source_tag} {article['regulation_id']} — Pasal {article['article_number']}"
        parts.append(f"{header}\n{article['text']}")
    return "\n\n---\n\n".join(parts)


def _build_prompt(question: str, context: str) -> str:
    return (
        f"Konteks peraturan:\n\n{context}\n\n"
        f"Pertanyaan: {question}\n\n"
        "Jawaban:"
    )
