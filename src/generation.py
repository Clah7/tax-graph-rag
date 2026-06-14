"""
generation.py — Shared prompt assembly and context formatting.

BaselineRAGPipeline and GraphRAGPipeline both call into this module so that
the only variable between the two systems is the set of retrieved articles
(not the prompt, the context format, or the LLM call).
"""
from typing import Any

SYSTEM_PROMPT = """Anda adalah asisten hukum pajak Indonesia yang ahli dalam peraturan perpajakan.
Jawablah pertanyaan pengguna berdasarkan konteks pasal-pasal peraturan yang diberikan.
Sebutkan nomor pasal dan peraturan yang relevan dalam jawaban Anda.
Jika informasi tidak tersedia dalam konteks, katakan bahwa informasi tersebut tidak ditemukan dalam peraturan yang ada."""


def format_context(articles: list[dict[str, Any]]) -> str:
    parts = []
    for article in articles:
        source_tag = f"[{article['source'].upper()}]"
        header = f"{source_tag} {article['regulation_id']} — Pasal {article['article_number']}"
        parts.append(f"{header}\n{article['text']}")
    return "\n\n---\n\n".join(parts)


def build_prompt(question: str, context: str) -> str:
    return (
        f"Konteks peraturan:\n\n{context}\n\n"
        f"Pertanyaan: {question}\n\n"
        "Jawaban:"
    )
