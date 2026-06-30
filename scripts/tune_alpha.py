"""
tune_alpha.py — Sweep GRAPH_RERANK_ALPHA on the DEV split (retrieval-only).

Run:
    python -m scripts.tune_alpha                      # sweep grid on dev
    python -m scripts.tune_alpha --report-test 0.1    # single alpha on test

Why retrieval-only: the IR metrics (recall@k, mrr, hit@k) need only the ranked
article IDs, not generated answers — no LLM, so a full grid sweep takes seconds
of Neo4j/Chroma I/O instead of hours of generation. Each dev question is
`gather()`-ed once (the expensive, alpha-independent step); every alpha then
re-ranks the cached candidates in pure Python.

Methodology guard: the grid sweep reads ONLY the dev split. The test split is
touched only by the explicit, single-alpha `--report-test` mode — never swept —
so the held-out numbers are never fitted. alpha=0 == baseline retrieval exactly.
"""
import argparse
import json
from pathlib import Path

from src.config import BASE_DIR, GRAPH_CONTEXT_BUDGET
from src.evaluation.dataset import load_dataset
from src.evaluation.ir_metrics import score_row
from src.graph_rag.retriever import gather, rerank

SPLIT_PATH = Path(BASE_DIR) / "data" / "ground_truth" / "split.json"
GRID = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0]


def _load_split() -> dict:
    if not SPLIT_PATH.exists():
        raise SystemExit("No split.json — run `python -m scripts.make_split` first.")
    return json.loads(SPLIT_PATH.read_text(encoding="utf-8"))


def _eval_alpha(bundles: list[tuple], alpha: float) -> dict[str, float]:
    """Mean IR metrics over pre-gathered (gold, hop_type, bundle) tuples."""
    rows = []
    for gold, _hop, bundle in bundles:
        ranked = rerank(bundle, alpha=alpha, budget=GRAPH_CONTEXT_BUDGET)
        retrieved = [a["id"] for a in ranked]
        rows.append(score_row(gold, retrieved))
    n = len(rows)
    keys = ("recall@5", "precision@5", "hit@5", "mrr")
    return {k: sum(r[k] for r in rows) / n for k in keys}


def _gather_split(ids: set[str]) -> list[tuple]:
    items = [it for it in load_dataset() if it.id in ids]
    bundles = []
    for it in items:
        bundles.append((it.gold_article_ids, it.hop_type, gather(it.question)))
    return bundles


def sweep_dev(split: dict) -> None:
    dev_ids = set(split["dev"])
    print(f"Gathering {len(dev_ids)} dev questions (one-time)...")
    bundles = _gather_split(dev_ids)

    print(f"\nDEV sweep (n={len(bundles)}, budget={GRAPH_CONTEXT_BUDGET})")
    print(f"{'alpha':>6}  {'recall@5':>9}  {'prec@5':>7}  {'hit@5':>6}  {'mrr':>6}")
    best = None
    for alpha in GRID:
        m = _eval_alpha(bundles, alpha)
        tag = "  (== baseline)" if alpha == 0.0 else ""
        print(f"{alpha:>6.3g}  {m['recall@5']:>9.4f}  {m['precision@5']:>7.4f}  "
              f"{m['hit@5']:>6.4f}  {m['mrr']:>6.4f}{tag}")
        key = (round(m["recall@5"], 6), round(m["mrr"], 6))
        if best is None or key > best[0]:
            best = (key, alpha, m)

    _, alpha, m = best
    print(f"\nBest on DEV: alpha={alpha:g}  recall@5={m['recall@5']:.4f}  mrr={m['mrr']:.4f}")
    print("Set GRAPH_RERANK_ALPHA in src/config.py to this value, then:")
    print(f"  python -m scripts.tune_alpha --report-test {alpha:g}")


def report_test(split: dict, alpha: float) -> None:
    test_ids = set(split["test"])
    print(f"Gathering {len(test_ids)} TEST questions...")
    bundles = _gather_split(test_ids)
    m = _eval_alpha(bundles, alpha)
    base = _eval_alpha(bundles, 0.0)
    print(f"\nHELD-OUT TEST (n={len(bundles)}), alpha={alpha:g}")
    print(f"{'metric':>10}  {'baseline':>9}  {'graph':>9}  {'delta':>8}")
    for k in ("recall@5", "precision@5", "hit@5", "mrr"):
        print(f"{k:>10}  {base[k]:>9.4f}  {m[k]:>9.4f}  {m[k]-base[k]:>+8.4f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-test", type=float, metavar="ALPHA",
                    help="Evaluate a single chosen alpha on the held-out test split.")
    args = ap.parse_args()

    split = _load_split()
    if args.report_test is not None:
        report_test(split, args.report_test)
    else:
        sweep_dev(split)


if __name__ == "__main__":
    main()
