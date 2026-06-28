# 0006 — Article-ID collisions: omnibus laws + penjelasan-as-article

- **Status:** Proposed
- **Date:** 2026-06-29

## Context

While sourcing tax questions for the eval set, the gold-text lookups for several
core laws (UU 7/2021 HPP, UU 6/1983 KUP, UU 10/2020 Bea Meterai, UU 42/2009 PPN)
returned the **Penjelasan** (elucidation) or a `"Cukup jelas."` stub instead of
the operative provision (batang tubuh). Investigation of
`data/processed/articles.json` (the parser output, source of truth) found the
identity key `(regulation_id, article_number)` collapses genuinely distinct
records:

- 118,966 unique `(reg, pasal)` groups.
- **19,246 (16.2%)** of those groups have >1 raw record.
- **6,031 (~5%)** have ≥2 *distinct substantive* bodies (>200 chars) — i.e. real,
  different provisions merged under one ID.
- 640 groups whose surviving text is empty / `"Cukup jelas."`.

Two independent root causes:

1. **Omnibus / amendment laws reuse Pasal numbers.** UU 7/2021 (HPP) amends KUP,
   PPh, and PPN, so "Pasal 9" exists once per embedded law. `UU 7 TAHUN 2021::9`
   has 7 raw records — among them the amended UU PPh Pasal 9 (non-deductibles)
   and the amended UU PPN Pasal 9 (Pajak Masukan/Keluaran) — which are different
   norms. `(regulation_id, article_number)` cannot disambiguate them.
2. **Penjelasan captured as a sibling "article"** with the same Pasal number as
   its batang tubuh, so body and elucidation collide.

**Dedup keeps the LAST record arbitrarily, not the batang tubuh:**
- Baseline/Chroma: `baseline_rag/ingestion.py` — `seen[id] = a` ("keep last
  occurrence").
- Graph/Neo4j: `graph_rag/ingestion.py` `_ingest_articles` —
  `MERGE (a:Article {id}) ... ON MATCH SET a.text = $text` (last write wins).

Both iterate the same `articles.json`, so the two stores stay consistent with
each other — but consistently keep whichever record happens to be last, which
for `UU 7/2021::9` is the `"Cukup jelas."` stub.

## Consequences (why this blocks the thesis)

- **Gold labeling:** a gold ID can pass `validate_ground_truth.py` (it *exists*)
  yet resolve to the wrong provision or `"Cukup jelas."`. Existence ≠ correctness;
  the validator must also reject trivial/penjelasan survivors.
- **Both RAG corpora:** ~5% of articles silently hold wrong or elucidation text,
  degrading retrieval for baseline and graph alike — unpredictably, since the
  surviving record is arbitrary.
- **Supersedes the identity model in ADR 0001:** `(regulation_id,
  article_number)` is insufficient for omnibus/amendment laws.
- Distinct from, and larger than, the OCR `O`→`0` issue (ADR 0003).

## Decision (proposed — fix scope to confirm before re-ingest)

1. **Dedup must prefer batang tubuh, not last-seen.** Minimum: keep the longest
   non-penjelasan record per ID; drop `"Cukup jelas."`/empty survivors.
2. **Disambiguate omnibus collisions.** Options to evaluate:
   (a) extend the ID with the embedded-law / structural context the parser can
   recover; (b) detect amended-law blocks during parsing and namespace the Pasal.
3. **Penjelasan handling.** Either attach elucidation to its batang tubuh as a
   separate field, or tag and exclude penjelasan records from `:Article` text.
4. **Harden `validate_ground_truth.py`** to flag gold IDs whose resolved text is
   trivial/penjelasan, not just missing.

Mechanism, exact ID scheme, and whether to re-parse vs. migrate are open; record
the final choice here before re-ingesting. Eval-question drafting is paused until
the corpus is corrected, then resumes sourcing only from verified-clean records.

## Status of related work

- Eval set: 10 verified (q001–q010); their gold text should be re-checked
  against this issue (they use PP 53/2010, UU 13/2003, PMK 82/2024, PMK 168/2023).
- Question drafting toward 50 is paused pending this fix (TODO §1).
