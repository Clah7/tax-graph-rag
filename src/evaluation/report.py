"""
report.py — Aggregate IR + Ragas scores, write per-row CSV and a summary
table sliced by hop_type.

Outputs:
    data/eval_runs/_reports/<tag>_per_question.csv   one row per (system, qid)
    data/eval_runs/_reports/<tag>_summary.csv        means + paired tests
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict
from pathlib import Path

from src.config import BASE_DIR
from src.evaluation.ir_metrics import score_row
from src.evaluation.runner import RunResult, load_run
from src.evaluation.stats import paired_test

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(BASE_DIR) / "data" / "eval_runs" / "_reports"
DEFAULT_K_VALUES = (1, 3, 5, 10, 20)


def _ir_rows(results: list[RunResult], k_values: tuple[int, ...]) -> list[dict]:
    rows = []
    for r in results:
        scores = score_row(r.gold_article_ids, r.retrieved_ids, k_values=k_values)
        rows.append({
            "id": r.id,
            "system": r.system,
            "hop_type": r.hop_type,
            "n_gold": len(r.gold_article_ids),
            "n_retrieved": len(r.retrieved_ids),
            "latency_s": r.latency_s,
            **scores,
        })
    return rows


def _merge_ragas(rows: list[dict], ragas_scores: list[dict] | None) -> list[dict]:
    if not ragas_scores:
        return rows
    if len(ragas_scores) != len(rows):
        logger.warning("Ragas score count (%d) != row count (%d); skipping merge.",
                       len(ragas_scores), len(rows))
        return rows
    for row, scored in zip(rows, ragas_scores):
        for k, v in scored.items():
            row[f"ragas_{k}"] = v
    return rows


def build_report(
    baseline_results: list[RunResult],
    graph_results: list[RunResult],
    tag: str = "default",
    baseline_ragas: list[dict] | None = None,
    graph_ragas: list[dict] | None = None,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
) -> dict[str, Path]:
    import pandas as pd

    # Per-question table (long format)
    base_rows = _merge_ragas(_ir_rows(baseline_results, k_values), baseline_ragas)
    graph_rows = _merge_ragas(_ir_rows(graph_results, k_values), graph_ragas)
    per_q = pd.DataFrame(base_rows + graph_rows)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    per_q_path = REPORTS_DIR / f"{tag}_per_question.csv"
    per_q.to_csv(per_q_path, index=False)
    logger.info("Per-question table -> %s", per_q_path)

    # Summary: paired tests on metrics shared between both systems
    metric_cols = [c for c in per_q.columns
                   if c not in {"id", "system", "hop_type", "n_gold", "n_retrieved"}]

    by_id = {(r["id"], r["system"]): r for r in per_q.to_dict("records")}
    qids = sorted({r["id"] for r in base_rows} & {r["id"] for r in graph_rows})
    hop_by_id = {r["id"]: r["hop_type"] for r in base_rows}

    summary_rows = []
    for slice_name, slice_qids in [
        ("all", qids),
        ("single", [q for q in qids if hop_by_id.get(q) == "single"]),
        ("multi",  [q for q in qids if hop_by_id.get(q) == "multi"]),
    ]:
        if not slice_qids:
            continue
        for metric in metric_cols:
            base_vals  = [_as_float(by_id[(q, "baseline")].get(metric)) for q in slice_qids]
            graph_vals = [_as_float(by_id[(q, "graph")].get(metric))    for q in slice_qids]
            res = paired_test(metric, base_vals, graph_vals)
            summary_rows.append({"slice": slice_name, **asdict(res)})

    summary = pd.DataFrame(summary_rows)
    summary_path = REPORTS_DIR / f"{tag}_summary.csv"
    summary.to_csv(summary_path, index=False)
    logger.info("Summary table -> %s", summary_path)

    return {"per_question": per_q_path, "summary": summary_path}


def _as_float(v) -> float:
    if v is None:
        return float("nan")
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x if not math.isnan(x) else float("nan")


def report_from_runs(
    run_id: str = "default",
    tag: str | None = None,
    with_ragas: bool = False,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
) -> dict[str, Path]:
    tag = tag or run_id
    base = load_run("baseline", run_id)
    grph = load_run("graph", run_id)
    if not base or not grph:
        raise RuntimeError(
            f"Missing runs for run_id={run_id!r}: baseline={len(base)}, graph={len(grph)}. "
            "Run both pipelines first via `python -m src.evaluation run --system <name>`."
        )

    base_ragas = grph_ragas = None
    if with_ragas:
        from src.evaluation.ragas_metrics import score_with_ragas
        base_ragas = score_with_ragas(base)
        grph_ragas = score_with_ragas(grph)

    return build_report(base, grph, tag=tag,
                        baseline_ragas=base_ragas, graph_ragas=grph_ragas,
                        k_values=k_values)
