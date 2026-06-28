# 0002 — Hold out eval test split before tuning

- **Status:** Accepted
- **Date:** 2026-05-25

## Context

The thesis compares Baseline RAG vs GraphRAG. Retrieval has tunable
hyperparameters (`TOP_K_VECTOR`, `GRAPH_HOP_DEPTH`). With a single small
hand-labeled set (~50 questions), tuning and evaluating on the same data inflates
results and is indefensible in a viva. Gold labels are also hand-authored by the
researcher, so over-fitting to one's own labels is a real risk.

## Decision

- Before any hyperparameter tuning, freeze a held-out test split.
- Shuffle the 50 questions with a fixed seed; first 35 → `eval.dev.jsonl` (tune
  here), last 15 → `eval.test.jsonl` (run only at the very end).
- Stratify the split to preserve the 60/40 multi/single-hop ratio in both files.
- Report final numbers on the frozen test split only.

## Consequences

- Lower variance risk and a defensible methodology claim.
- 15 test questions is small — pair the analysis per-question (Wilcoxon
  signed-rank / paired t-test) to retain statistical power.
- `src/evaluation/dataset.py` must accept a path argument rather than hardcoding
  one file.
