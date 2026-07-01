"""
runner.py — Run a pipeline over the eval set and persist outputs.

Generation is the expensive step (Ollama, ~5–20s per question). We cache the
per-question (answer, retrieved articles) to disk so:

  1. IR metrics can be recomputed without re-querying.
  2. Ragas (LLM-judge) can be re-scored with a different judge model later.
  3. A crashed run can be resumed: items already in the cache are skipped.

Output layout:
    data/eval_runs/<system>/<run_id>.jsonl    one JSON object per question
"""
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.config import BASE_DIR
from src.evaluation.dataset import EvalItem, load_dataset

logger = logging.getLogger(__name__)

RUNS_DIR = Path(BASE_DIR) / "data" / "eval_runs"


@dataclass
class RunResult:
    id: str
    question: str
    gold_article_ids: list[str]
    gold_answer: str
    hop_type: str
    answer: str
    retrieved_ids: list[str]
    contexts: list[str]
    sources: list[str]
    latency_s: float
    system: str
    meta: dict[str, Any] = field(default_factory=dict)


def _system_to_pipeline(system: str, alpha: float | None = None):
    if system == "baseline":
        from src.baseline_rag.pipeline import BaselineRAGPipeline
        return BaselineRAGPipeline()
    if system == "graph":
        from src.graph_rag.pipeline import GraphRAGPipeline
        from src.config import GRAPH_RERANK_ALPHA
        return GraphRAGPipeline(alpha=GRAPH_RERANK_ALPHA if alpha is None else alpha)
    raise ValueError(f"Unknown system: {system!r} (expected 'baseline' or 'graph').")


def _output_path(system: str, run_id: str) -> Path:
    path = RUNS_DIR / system / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_completed(path: Path) -> dict[str, RunResult]:
    if not path.exists():
        return {}
    done: dict[str, RunResult] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            done[row["id"]] = RunResult(**row)
    return done


def run_system(
    system: str,
    run_id: str = "default",
    items: list[EvalItem] | None = None,
    pipeline: Any = None,
    resume: bool = True,
    alpha: float | None = None,
    run_meta: dict[str, Any] | None = None,
) -> list[RunResult]:
    """
    Run `system` over the eval set; append RunResult rows to disk as they
    complete. Returns the full list of RunResults including any that were
    resumed from cache. `run_meta` is stamped on every result for provenance
    (e.g. seeding mode + alpha), so a run file records the config that made it.
    """
    if items is None:
        items = load_dataset()
    if pipeline is None:
        pipeline = _system_to_pipeline(system, alpha=alpha)

    path = _output_path(system, run_id)
    completed = _load_completed(path) if resume else {}
    if completed:
        logger.info("Resuming: %d/%d items already in %s.", len(completed), len(items), path)

    results: list[RunResult] = list(completed.values())
    with open(path, "a", encoding="utf-8") as fh:
        for item in items:
            if item.id in completed:
                continue
            logger.info("[%s] %s — %s", system, item.id, item.question[:80])
            t0 = time.perf_counter()
            try:
                out = pipeline.query(item.question)
            except Exception:
                logger.exception("[%s] %s failed; skipping.", system, item.id)
                continue
            latency = time.perf_counter() - t0

            ctx = out["context"]
            result = RunResult(
                id=item.id,
                question=item.question,
                gold_article_ids=item.gold_article_ids,
                gold_answer=item.gold_answer,
                hop_type=item.hop_type,
                answer=out["answer"],
                retrieved_ids=[a["id"] for a in ctx],
                contexts=[a["text"] for a in ctx],
                sources=[a.get("source", "") for a in ctx],
                latency_s=latency,
                system=system,
                meta=dict(run_meta or {}),
            )
            fh.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            fh.flush()
            results.append(result)

    logger.info("[%s] run %r complete: %d results -> %s", system, run_id, len(results), path)
    return results


def load_run(system: str, run_id: str = "default") -> list[RunResult]:
    path = _output_path(system, run_id)
    return list(_load_completed(path).values())


def run_callable(
    fn: Callable[[str], dict[str, Any]],
    system_label: str,
    run_id: str = "default",
    items: list[EvalItem] | None = None,
    resume: bool = True,
) -> list[RunResult]:
    """Escape hatch: run any callable(question)->{answer, context} as `system_label`."""
    class _Adapter:
        def query(self, q: str) -> dict[str, Any]:
            return fn(q)
    return run_system(system_label, run_id, items=items, pipeline=_Adapter(), resume=resume)
