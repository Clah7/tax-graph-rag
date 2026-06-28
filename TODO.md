# Roadmap

Ordered by priority. Tick items as done; move detail into `docs/` or a
decision record when it stabilises.

## 0. (BLOCKER) Fix article-ID collisions — ADR 0006

Found 2026-06-29 while sourcing tax questions. `(regulation_id, article_number)`
merges distinct provisions: omnibus laws (UU 7/2021 amends KUP/PPh/PPN) reuse
Pasal numbers, and Penjelasan collides with batang tubuh. ~5% of articles hold
≥2 distinct merged bodies; dedup keeps the last record arbitrarily (can be a
`"Cukup jelas."` stub). Degrades both RAG corpora and makes gold text unreliable.

- [ ] Dedup: prefer batang tubuh (longest non-penjelasan), drop trivial survivors.
- [ ] Disambiguate omnibus collisions (ID scheme — see ADR 0006).
- [ ] Harden `validate_ground_truth.py` to flag penjelasan/trivial resolved text.
- [ ] Re-ingest or migrate; re-check q001–q010 gold text afterward.

## 1. Hand-label ground-truth set — target 50 questions

`data/ground_truth/eval.jsonl` has 10 entries (q001–q010), all `VERIFIED`.
Full procedure in `docs/building-eval-dataset.md`.
**Drafting toward 50 is PAUSED pending §0 (ADR 0006).**

- [x] Verify the 10 drafts against source text (`DRAFT` → `VERIFIED`). (2026-06-28)
- [ ] (blocked by §0) Compose ~60% multi-hop / ~40% single-hop; spread across
      PMK/PP/UU/Perpu/Perpres; no single topic > ~20% (≤10 questions). Decided
      2026-06-29: tax-focused; PMK/UU/PP + a little Perpu (no Perpres — absent
      from corpus); next batch of 10 leans 6 multi / 4 single.
- [x] Write `scripts/validate_ground_truth.py` (resolve every gold ID against
      ChromaDB and Neo4j). 13/13 IDs resolve in both stores. (2026-06-28)
- [x] Pilot at N=10, dry-run the eval harness end-to-end (run-id `pilot10`,
      baseline+graph → report, paired stats). Surfaced the matched-depth issue
      (ADR 0005). (2026-06-28) — then scale to 50.
- [ ] Freeze a held-out 30% (15 q) test split *before* any tuning (ADR 0002).

## 2. Evaluation harness — `src/evaluation/`

- [ ] Retrieval metrics vs `gold_article_ids`: Recall@K, Precision@K, MRR.
- [ ] Generation metrics vs `gold_answer`: LLM-as-judge faithfulness + correctness.
- [ ] Paired per-question delta between pipelines; Wilcoxon signed-rank / paired t-test.
- [x] **Unit-test the metric functions** with hand-computed cases — this is the
      thesis's measuring instrument; a silent bug here invalidates the conclusion.
      `tests/test_ir_metrics.py`, 28 cases, all pass. (2026-06-28)

## 3. (Lower) OCR `O`→`0` fix

After the harness exists, decide whether the 0.2% poisoned IDs move metrics
enough to justify a rebuild. If yes, migration script (option b) beats re-parse.

## 4. (Lower) `_ingest_definitions` perf

Refactor the cartesian pattern. Only matters if rebuilding the graph repeatedly.

## Housekeeping

- [ ] **Rotate the Neo4j password** — the old one is still in git history (the
      `.env` move only fixes the working tree). Change it in Neo4j + update
      `.env`; optionally `git filter-repo` to scrub history. See ADR 0004.
