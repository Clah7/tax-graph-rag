# 0003 — Defer the OCR `O`→`0` fix; re-ingest as-is

- **Status:** Accepted
- **Date:** 2026-05-25

## Context

~287 of 118,966 article rows (~0.2%) have a capital `O` where digit `0` belongs
(`Pasal 1O`, `10O`). This corrupts article identity (ADR 0001): it causes
seed/graph dedup misses and accounts for most of the ~20k `REFERENCES` edges
that were attempted but didn't resolve to a target `:Article`. A clean fix
(normalise in `parser.py`) requires a full re-ingest, including ~5h of baseline
embedding.

## Decision

Re-ingest as-is for now and defer the fix. Revisit only after the eval harness
exists, when the impact on metrics can be measured rather than assumed.

## Consequences

- ~0.2% of articles and a slice of reference edges are knowingly degraded.
- If a gold article id lands on a corrupted row, it becomes unmatchable — the
  `validate_ground_truth.py` checker (see `docs/building-eval-dataset.md` §3)
  must flag this so gold labels avoid corrupted ids.
- When revisited: option (a) normalise in `parser.py` + re-ingest (cleaner);
  option (b) migration script over `articles.json` + Chroma + Neo4j (saves ~5h).
