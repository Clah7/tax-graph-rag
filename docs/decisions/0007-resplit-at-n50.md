# 0007 — Fresh stratified re-split at n=50

- **Status:** Accepted
- **Date:** 2026-07-05
- **Supersedes:** the n=24 split under [0002](0002-held-out-test-split.md)

## Context

ADR 0002 froze a dev/test split, but at the time the eval set only covered
q001–q024 (dev=8 / test=16); q025–q031 were unassigned. The set has since grown
to **50 questions** (q001–q050). A stale split covering half the set is not usable
for the final headline, and every downstream artifact (bootstrap CIs, RAGAS,
BAB IV) is gated on a frozen split at the target size.

The ADR 0002 discipline — *hold out the test split before tuning* — exists so the
reported numbers are not fitted to the data they are measured on. The graph stage
has one tunable knob, `GRAPH_RERANK_ALPHA`.

## Decision

Draw a **fresh stratified split over all 50 rows** with `scripts/make_split.py`
(`seed=20260701`, `dev_frac=0.34`), overwriting `data/ground_truth/split.json`.

This full re-split is sound despite ADR 0002 **because alpha is frozen at 0.10 and
is not re-tuned after the re-split** — nothing is fitted to the new test set, so a
row moving from old-dev to new-test cannot leak. The split is reproducible from
`(seed, dev_frac)` and stratified by `hop_type`.

### Result (n=50)

- **dev = 17** (7 single / 10 multi), **test = 33** (14 single / 19 multi).
- Cross-regulation multi-hops distribute **5 dev / 8 test** — the thesis's sharp
  slice is well-represented on the reported (test) side. (`make_split` stratifies
  on `hop_type` only; this cross-reg balance was checked manually and is adequate,
  so no re-seed needed.)
- Test n=33 roughly doubles the old n=16 → ~2× statistical power.

### Superseded split (for provenance)

- Old (n=24, seed 20260701): dev = q005–q007, q012, q013, q018, q022, q024;
  test = q001–q004, q008–q011, q014–q017, q019–q021, q023.

## Consequences

- The old headline (test n=16) is superseded; re-run the 2×2 on the new test split
  (Phase 5) with alpha frozen (0.10 hybrid, 0.15 dense ablation) and bootstrap CIs.
- **Provisional until verification:** the 19 new rows are still `DRAFT`. If the
  human verify pass reclassifies any `hop_type`, re-run `make_split` (idempotent)
  before the final 2×2. q035 was already reclassified multi→single during
  pre-freeze gold adjudication (see `docs/research-log.md`, 2026-07-05).
