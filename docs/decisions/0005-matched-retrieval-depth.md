# 0005 — Compare pipelines at matched retrieval depth

- **Status:** Proposed
- **Date:** 2026-06-28

## Context

The N=10 dry-run (`run-id pilot10`) exposed an apples-to-oranges comparison in
the rank-cutoff metrics. `TOP_K_VECTOR = 5`, so the **baseline** pipeline never
returns more than 5 articles: its `recall@10` and `recall@20` are pinned equal
to its `recall@5` (0.433 in the pilot) because ranks 6–20 are empty. The
**graph** pipeline expands to ~40 context articles, so its recall keeps growing
past k=5 (pilot: recall@20 0.43 → 0.67; multi-hop 0.39 → 0.78).

Reported naively, graph's `recall@{10,20}` "wins" partly reflect that it is
*allowed* to return more candidates, not that its retrieval is better at a fixed
budget. At k ≤ 5 the two systems are identical (they share `vector_search`
Stage 1), confirming the divergence is purely an artifact of unequal depth.

## Decision

Compare the two pipelines at **matched retrieval depth**. Concretely, before the
real evaluation runs:

- Report IR metrics only at k values both systems can populate (primary
  headline metric: a k ≤ retrieval budget), OR
- Raise the baseline's candidate count so both return the same N, and document
  the chosen N.

Precision@k stays meaningful at any k (it already penalises graph's larger
candidate set), so the asymmetry is specifically a recall/hit@k-at-large-k
problem. Decide the exact mechanism (cap graph vs. widen baseline) and the
headline k when scaling past the pilot; record the final choice here before the
test split is unfrozen.

## Consequences

- Recall@10 / recall@20 from `pilot10` are **not** a valid baseline-vs-graph
  signal as-is — treat them as a harness smoke test only, not a result.
- The fairness mechanism must be fixed and documented *before* tuning, alongside
  the held-out split (ADR 0002), so the comparison is defensible in the viva.
- `report.py`'s default `k_values=(1,3,5,10,20)` can still be computed; the
  thesis narrative must just foreground a matched-depth k.
