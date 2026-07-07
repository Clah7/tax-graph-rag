"""
ragas_stats.py — Stage B of the generation-side eval.

Reads the two per-row RAGAS score JSONLs written by `scripts/ragas_score.py`
(baseline vs graph, same run/split) and emits the paired comparison per metric:
mean baseline/graph, delta, bootstrap 95% CI, Wilcoxon + paired-t p, win/loss.

Run under the `skripsi` env (has scipy + the src package). This is the same
`src.evaluation.stats.paired_test` used for the IR metrics, so the generation
side is reported on identical statistical footing.

Usage:
    python scripts/ragas_stats.py \
        --baseline data/eval_runs/_reports/ragas/baseline_hyb_test_v50.jsonl \
        --graph    data/eval_runs/_reports/ragas/graph_hyb_test_v50.jsonl \
        --out      data/eval_runs/_reports/ragas/hyb_test_v50_stats.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math

from src.evaluation.stats import paired_test

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
]


def _load(path: str) -> dict[str, dict]:
    out = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[r["id"]] = r
    return out


def _aligned(baseline: dict, graph: dict, metric: str, ids: list[str]):
    b = [float(baseline[i].get(metric, float("nan"))) for i in ids]
    g = [float(graph[i].get(metric, float("nan"))) for i in ids]
    return b, g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--metrics", nargs="+", default=METRIC_NAMES)
    ap.add_argument("--hop", choices=["all", "single", "multi"], default="all")
    args = ap.parse_args()

    base = _load(args.baseline)
    grph = _load(args.graph)
    ids = sorted(set(base) & set(grph))
    if args.hop != "all":
        ids = [i for i in ids if base[i].get("hop_type") == args.hop]
    print(f"[stats] {len(ids)} paired ids (hop={args.hop})")

    fields = ["metric", "n", "mean_baseline", "mean_graph", "mean_delta",
              "median_delta", "ci_low", "ci_high", "wilcoxon_p", "t_p",
              "wins_graph", "wins_baseline", "ties"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in args.metrics:
            b, g = _aligned(base, grph, m, ids)
            res = paired_test(m, b, g)
            w.writerow({k: getattr(res, k) for k in fields})
            print(f"[{m:22s}] base={res.mean_baseline:.3f} graph={res.mean_graph:.3f} "
                  f"Δ={res.mean_delta:+.3f} CI[{res.ci_low:+.3f},{res.ci_high:+.3f}] "
                  f"p={res.wilcoxon_p:.3f} {res.wins_graph}W/{res.wins_baseline}L")
    print(f"[stats] wrote {args.out}")


if __name__ == "__main__":
    main()
