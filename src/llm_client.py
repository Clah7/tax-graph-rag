"""
llm_client.py — Thin wrappers around Ollama for embedding and text generation.
"""
import requests
from src.config import OLLAMA_BASE_URL, EMBED_MODEL, LLM_MODEL


def embed(texts: list[str]) -> list[list[float]]:
    """Return 1024-dim embeddings for a list of texts."""
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    resp.raise_for_status()
    embeddings: list[list[float]] = resp.json()["embeddings"]
    if len(embeddings) != len(texts):
        raise ValueError(f"Expected {len(texts)} embeddings, got {len(embeddings)}")
    return embeddings


def generate(prompt: str, system: str = "") -> str:
    """Call the Ollama chat endpoint and return the assistant message."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": LLM_MODEL, "messages": messages, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]
