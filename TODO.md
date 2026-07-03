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

`data/ground_truth/eval.jsonl` has **31 entries, all `VERIFIED`
(q001–q031)**. Full procedure in `docs/building-eval-dataset.md`. **Toward 50.**
n=16 test is underpowered to detect a modest graph effect, so growing the set is
also a stats priority.

- [x] Verify the 10 drafts against source text (`DRAFT` → `VERIFIED`). (2026-06-28)
- [x] q011–q024 authored + verified (2026-06-29): Bea Materai (UU 10/2020),
      PPh final UMKM (PP 23/2018 ↔ PMK 99/2018, cross-reg), PDRD (UU 28/2009).
- [x] **Verify q025–q031** (2026-07-04): PBB-P2, PBJT, MBLB (UU 1/2022 HKPD),
      PPN hasil tembakau / LPG tertentu (PMK 63,62/2022), Pajak Masukan, Pajak
      Reklame. `validate_ground_truth` clean (51/51 IDs resolve, 0 trivial);
      each `gold_answer` hand-checked verbatim. Flag: q028/q029 are weak
      intra-reg multi-hops (compute+tarif in the higher article) — reclassify
      single or replace with cross-reg pairs later.
- [ ] **Re-split decision** once verified: the frozen dev=8/test=16 split covers
      only q001–q024 (ADR 0002). Decide how q025+ enter dev/test **without
      touching the current held-out test** (e.g. add to dev, or draw a fresh
      stratified split and re-freeze) — do this *before* any further tuning.
- [ ] **Continue to 50 — target composition** (literature-grounded, see
      STATUS "Ground-truth target composition"). Author the remaining 19 as
      **9 multi + 10 single** to land the final 50 at **30 multi / 20 single
      (60/40)**. Make **all 9 new multi cross-regulation** (gold IDs span ≥2
      regs) → cross-reg 4→13 (~43% of multi), GraphRAG's sharpest case. Every
      new multi must pass the **non-skippability gate** (drop either gold
      article ⇒ answer wrong/incomplete; MuSiQue criterion). Tax-focused;
      PMK/UU/PP + a little Perpu (no Perpres — absent from corpus); keep every
      regulation ≤10 rows (≤20%) — UU 28/2009 is at 6, **freeze it**; introduce
      2–3 new families rather than deepening existing ones. Sources: prefer the
      norm↔pelaksana delegation pattern (UU → PP/PMK), the q015–q018 shape.
- [ ] **Reclassify or fix q028/q029** under the non-skippability gate before
      the final freeze — they are skippable intra-reg multi-hops (compute+tarif
      sits in the higher article; the lower one only supplies the object framing).
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
- [ ] **Add paired bootstrap 95% CIs** on the per-question metric deltas
      (10,000 resamples) alongside the Wilcoxon p — the standard small-n
      presentation (RAG-eval survey, arXiv 2405.07437). Report effect + CI, not
      p alone, and state the n-underpowered caveat explicitly in BAB IV.
- [ ] Generation metrics vs `gold_answer`: LLM-as-judge faithfulness + correctness
      (RAGAS). **Still untested axis** — graph context may improve answers even
      when ID-recall ties. Run on the test split once seeding lands.
- [x] **Unit-test the metric functions** with hand-computed cases — this is the
      thesis's measuring instrument; a silent bug here invalidates the conclusion.
      `tests/test_ir_metrics.py`, 28 cases, all pass. (2026-06-28)

## 2a. Hybrid lexical+dense seeding — DONE (retrieval IR); graph win found

Diagnosis (2026-07-01): seeding, not ranking, is the retrieval bottleneck —
41/44 gold IDs are within the dense top-200 but buried below top-5.

- [x] `src/hybrid_search.py` (dense top-N pool ⊕ BM25 re-rank ⊕ RRF k=60, no
      global index) + `src/seeding.py` dispatch on `USE_HYBRID_SEEDING` (toggle,
      default off — pure-vector baseline retained). Commit `69e8c99`.
- [x] Re-tuned alpha on hybrid dev (=0.10), reported the 2×2 on held-out test.
      **hybrid+graph recall@5 .698, hit@5 .938** vs dense-baseline .469/.625.
      Graph is null on dense seeds, decisive on hybrid seeds. STATUS.md has table.
- [x] `eval run --hybrid/--alpha/--split` flags (commit `17ec12a`); rows stamped
      with `meta={seeding,alpha,split}`. Ran the 2×2 on test (`dense_test`,
      `hyb_test`): hybrid+graph recall@5 0.698 vs hybrid-baseline 0.521,
      **Wilcoxon p=0.026, 6 wins / 0 losses**; dense+graph null.
- [x] **Framing call (thesis):** hybrid is the SHARED BASELINE (2026-07-01).
      `USE_HYBRID_SEEDING` defaults ON, `GRAPH_RERANK_ALPHA`=0.10 (hybrid-tuned);
      pure-vector retained as the toggle-off ablation floor. CLAUDE.md objective
      + config updated. Headline = `hyb_test`: graph .698 vs baseline .521.
- [ ] Generation-side eval (RAGAS) on the 2×2 — **deferred**: env `ragas` 0.4.3
      fails to import (`langchain_community.chat_models.vertexai` gone) and
      `ragas_metrics.py` targets ragas 0.1.x. Answers are cached, so it's a
      deps-pin + (ideally) a non-`qwen3.5:9b` judge away. See §2.
- [ ] Consider tuning HYBRID_POOL / RRF_K on dev (kept at defaults for now).

## 2b. Strict-parity graph re-ranker — DONE, null result

Commit `1005e85`. Symmetric, degree-damped `sim + alpha*boost`, truncated to the
TOP_K budget; `scripts.tune_alpha` (retrieval-only, dev-swept). Dev picked
alpha=0.15 but it is a **wash on held-out test** (recall@5 .469→.469, mrr
.424→.440). Latency/timeout/precision problems from the append-everything version
are fixed. Ranking is not the bottleneck — see §2a. Default `GRAPH_RERANK_ALPHA`
left at 0.15; revisit after hybrid seeding changes the candidate pool.

## 2c. Thesis writing — started 2026-07-02

Manuscript in Google Docs (Unpad format); Claude.ai Project as drafting assistant
grounded by `docs/context-packs/`. LaTeX scaffold in `thesis/` exists but is
untracked and secondary.

- [x] Context packs `docs/context-packs/{METHODOLOGY,RESULTS,GLOSSARY}.md`.
- [ ] **Re-sync `RESULTS.md`** whenever eval numbers change (static snapshot;
      currently the n=16 provisional 2×2). Re-upload to the Project after.
- [ ] Draft BAB I (Pendahuluan) and BAB III (Metodologi) first — best grounded.
- [ ] BAB II (Tinjauan Pustaka): author citations by hand — context packs carry
      NONE, to avoid fabricated references.
- [ ] BAB IV numbers stay provisional until the eval set is frozen at target.

## 3. (Lower) OCR `O`→`0` fix

After the harness exists, decide whether the 0.2% poisoned IDs move metrics
enough to justify a rebuild. If yes, migration script (option b) beats re-parse.

## 4. (Lower) `_ingest_definitions` perf

Refactor the cartesian pattern. Only matters if rebuilding the graph repeatedly.

## Housekeeping

- [ ] **Rotate the Neo4j password** — the old one is still in git history (the
      `.env` move only fixes the working tree). Change it in Neo4j + update
      `.env`; optionally `git filter-repo` to scrub history. See ADR 0004.
