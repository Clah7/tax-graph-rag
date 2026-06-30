# Roadmap

Ordered by priority. Tick items as done; move detail into `docs/` or a
decision record when it stabilises.

## 0. (BLOCKER) Fix article-ID collisions — ADR 0006

Found 2026-06-29 while sourcing tax questions. `(regulation_id, article_number)`
merges distinct provisions: omnibus laws (UU 7/2021 amends KUP/PPh/PPN) reuse
Pasal numbers, and Penjelasan collides with batang tubuh. ~5% of articles hold
≥2 distinct merged bodies; dedup keeps the last record arbitrarily (can be a
`"Cukup jelas."` stub). Degrades both RAG corpora and makes gold text unreliable.

- [x] Dedup: prefer batang tubuh (longest non-penjelasan), drop trivial
      survivors. `src/corpus.py` shared by both ingestions; tests in
      `tests/test_corpus.py`. (2026-06-29)
- [ ] Disambiguate omnibus collisions (ID scheme — see ADR 0006). ~1,157 cases,
      UU/PP/Perpu. Not started — the real design work.
- [x] Harden `validate_ground_truth.py` to flag penjelasan/trivial resolved text.
      Reuses `src.corpus._is_usable_body` so validator + dedup share one rule;
      now also fails (exit 1) on resolve-to-penjelasan. 0/13 flagged. (2026-06-29)
- [x] Apply to live stores. ChromaDB (2026-06-29): `migrate_dedup_text`
      re-embedded 18,255 docs; idempotency dry-run = 0 diffs; gold IDs 13/13.
      Embed-length fix landed (`1aa61ef`: cap + retry-on-400 shrink). Neo4j
      rebuilt (2026-06-29): wiped + re-ingested for correct text + REFERENCES/
      DEFINES; verified in sync (gold IDs 13/13, sampled text byte-identical).

## 1. Hand-label ground-truth set — target 50 questions

`data/ground_truth/eval.jsonl` has **24 entries (q001–q024), all `VERIFIED`**
(16 multi, 8 single). Full procedure in `docs/building-eval-dataset.md`.
**Toward 50 — resume after the seeding work (§2a).** n=16 test is underpowered
to detect a modest graph effect, so growing the set is also a stats priority.

- [x] Verify the 10 drafts against source text (`DRAFT` → `VERIFIED`). (2026-06-28)
- [x] q011–q024 authored + verified (2026-06-29): Bea Materai (UU 10/2020),
      PPh final UMKM (PP 23/2018 ↔ PMK 99/2018, cross-reg), PDRD (UU 28/2009).
- [ ] Continue to 50: tax-focused; PMK/UU/PP + a little Perpu (no Perpres —
      absent from corpus); ~60% multi / ~40% single; no single topic > ~20%.
- [x] Write `scripts/validate_ground_truth.py` (resolve every gold ID against
      ChromaDB and Neo4j). 36/36 IDs resolve in both stores. (2026-06-28→07-01)
- [x] Pilot at N=10, dry-run the eval harness end-to-end (run-id `pilot10`,
      baseline+graph → report, paired stats). Surfaced the matched-depth issue
      (ADR 0005). (2026-06-28)
- [x] Freeze a held-out test split *before* any tuning (ADR 0002).
      `data/ground_truth/split.json` via `scripts.make_split` — dev=8, test=16,
      stratified, seed 20260701. (2026-07-01)

## 2. Evaluation harness — `src/evaluation/`

- [x] Retrieval metrics vs `gold_article_ids`: Recall@K, Precision@K, MRR, hit@K.
- [x] Paired per-question delta between pipelines; Wilcoxon + paired t-test.
      `eval report` emits summary + per-question CSV (run v24/v25).
- [ ] Generation metrics vs `gold_answer`: LLM-as-judge faithfulness + correctness
      (RAGAS). **Still untested axis** — graph context may improve answers even
      when ID-recall ties. Run on the test split once seeding lands.
- [x] **Unit-test the metric functions** with hand-computed cases — this is the
      thesis's measuring instrument; a silent bug here invalidates the conclusion.
      `tests/test_ir_metrics.py`, 28 cases, all pass. (2026-06-28)

## 2a. (NEXT) Hybrid lexical+dense seeding

Diagnosis (2026-07-01): seeding, not ranking, is the retrieval bottleneck —
41/44 gold IDs are within the dense top-200 but buried below top-5. Prototype
(dense top-200 ⊕ BM25 pool re-rank, RRF k=60) lifts **held-out test** recall@5
.469→.521, hit@5 .625→.750, mrr .424→.547 — and generalizes (unlike the graph
re-rank, §2b, which was a wash on test). See STATUS.md "Retrieval & evaluation".

- [ ] Productionize `hybrid_search()` (no global BM25 index needed — re-rank the
      dense top-N pool). Add a config toggle; **keep pure-vector retained** for a
      (dense vs hybrid) × (baseline vs graph) ablation.
- [ ] Decide framing: hybrid as the new shared seeding (stronger baseline) vs
      toggle-only ablation. Affects what "baseline" denotes in the thesis.
- [ ] Re-run the 2×2 + re-tune alpha on hybrid seeds. Key question: do better
      seeds let graph expansion reach the cross-reg gold (q015–q018)?

## 2b. Strict-parity graph re-ranker — DONE, null result

Commit `1005e85`. Symmetric, degree-damped `sim + alpha*boost`, truncated to the
TOP_K budget; `scripts.tune_alpha` (retrieval-only, dev-swept). Dev picked
alpha=0.15 but it is a **wash on held-out test** (recall@5 .469→.469, mrr
.424→.440). Latency/timeout/precision problems from the append-everything version
are fixed. Ranking is not the bottleneck — see §2a. Default `GRAPH_RERANK_ALPHA`
left at 0.15; revisit after hybrid seeding changes the candidate pool.

## 3. (Lower) OCR `O`→`0` fix

After the harness exists, decide whether the 0.2% poisoned IDs move metrics
enough to justify a rebuild. If yes, migration script (option b) beats re-parse.

## 4. (Lower) `_ingest_definitions` perf

Refactor the cartesian pattern. Only matters if rebuilding the graph repeatedly.

## Housekeeping

- [ ] **Rotate the Neo4j password** — the old one is still in git history (the
      `.env` move only fixes the working tree). Change it in Neo4j + update
      `.env`; optionally `git filter-repo` to scrub history. See ADR 0004.
