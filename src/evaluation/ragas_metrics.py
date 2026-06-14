"""
ragas_metrics.py — Ragas (LLM-judge) generation-side metrics, wired to Ollama.

Ragas is an OPTIONAL dependency. If `ragas` / `langchain_ollama` aren't
installed the harness still produces IR metrics and stats; only the Ragas
columns are skipped.

Metrics scored here:
    - faithfulness         (answer claims supported by retrieved contexts)
    - answer_relevancy     (answer addresses the question)
    - answer_correctness   (answer matches `gold_answer`)
    - context_precision    (semantic — complements ID-based precision@k)
    - context_recall       (semantic — complements ID-based recall@k)

Caveat to disclose in the thesis: the judge model defaults to LLM_MODEL
(`qwen3.5:9b`) which is also the generator — this self-judging bias inflates
faithfulness and correctness. Override `llm_model=...` to a stronger judge
if available (e.g. via a different Ollama model or an API-backed wrapper).
"""
from __future__ import annotations

import logging
from typing import Any

from src.config import EMBED_MODEL, LLM_MODEL, OLLAMA_BASE_URL
from src.evaluation.runner import RunResult

logger = logging.getLogger(__name__)


def _build_evaluator(llm_model: str, embed_model: str, base_url: str):
    """Lazy-import Ragas + LangChain so the rest of the harness doesn't need them."""
    try:
        from langchain_ollama import ChatOllama, OllamaEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
    except ImportError as e:
        raise ImportError(
            "Ragas evaluation requires `ragas` and `langchain-ollama`. "
            "Install with: pip install ragas langchain-ollama"
        ) from e

    judge = LangchainLLMWrapper(ChatOllama(model=llm_model, base_url=base_url))
    emb   = LangchainEmbeddingsWrapper(OllamaEmbeddings(model=embed_model, base_url=base_url))
    return judge, emb


def _to_ragas_dataset(results: list[RunResult]):
    from datasets import Dataset
    rows = [{
        "question":     r.question,
        "answer":       r.answer,
        "contexts":     r.contexts,
        "ground_truth": r.gold_answer,
    } for r in results]
    return Dataset.from_list(rows)


def score_with_ragas(
    results: list[RunResult],
    llm_model: str = LLM_MODEL,
    embed_model: str = EMBED_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    metrics: list[Any] | None = None,
) -> list[dict[str, float]]:
    """
    Score each RunResult with Ragas. Returns a list of dicts aligned with
    `results` (same length, same order). Missing scores from Ragas (e.g. when
    `gold_answer` is empty) come back as NaN — caller decides how to handle.
    """
    from ragas import evaluate
    from ragas.metrics import (
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    if metrics is None:
        metrics = [faithfulness, answer_relevancy, answer_correctness,
                   context_precision, context_recall]

    judge, emb = _build_evaluator(llm_model, embed_model, base_url)
    dataset = _to_ragas_dataset(results)
    logger.info("Scoring %d items with Ragas (judge=%s).", len(results), llm_model)
    scored = evaluate(dataset, metrics=metrics, llm=judge, embeddings=emb)

    df = scored.to_pandas()
    metric_cols = [m.name for m in metrics]
    return df[metric_cols].to_dict(orient="records")
