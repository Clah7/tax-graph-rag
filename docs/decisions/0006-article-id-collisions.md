# 0006 — Article-ID collisions: omnibus laws + penjelasan-as-article

- **Status:** Dedup rule Accepted; omnibus ID scheme still Proposed
- **Date:** 2026-06-29 (prototype measurements added same day)

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

## Prototype measurements (`scripts/prototype_dedup.py`, 2026-06-29)

Testing the rule "keep the longest non-penjelasan, non-trivial record per ID"
(vs. current keep-last) over the 19,246 multi-record groups:

| Category | Count |
|---|---|
| Selectable — one batang tubuh after dropping penjelasan; simple rule fixes | 16,247 |
| Raw multi-body "collisions" | 2,990 |
| ...of which **true co-equal collisions** (≥2 distinct bodies, both >300 chars) | **1,157** |
| ...both bodies >1000 chars (hard core) | 445 |
| IDs whose text **changes** vs current keep-last | 18,264 |

The 2,990 raw collisions are mostly **lampiran/form fragments** mis-numbered as a
Pasal (e.g. `10/PMK.02/2017::23`, where the longest record is the real Pasal and
the extras are matrix rows) — longest-batang-tubuh-wins resolves these correctly.
True co-equal collisions concentrate in amendment/omnibus laws, by type:
**UU 617, PP 216, Perpu 152, PMK 35.** PMK is essentially clean after the simple
rule; the danger zone for eval sourcing is UU/PP/Perpu (e.g. UU 7/2021 HPP).

## Decision

1. **Dedup keeps the longest non-penjelasan, non-trivial record per ID** —
   *Accepted*. Resolves ~18k of 19,246 multi-record groups, including the
   lampiran artifacts. Implemented as a single shared loader (`src/corpus.py`)
   that both ingestions call, so Chroma and Neo4j stay identical by construction.
   The dedup logs a warning counting the ~1,157 true collisions where a co-equal
   provision is dropped, so they stay visible until (2) lands.
2. **Disambiguate omnibus collisions** — *still Proposed*. ~1,157 cases need an ID
   scheme, not selection. Options: (a) extend the ID with embedded-law/structural
   context the parser recovers; (b) detect amended-law blocks during parsing and
   namespace the Pasal. Decide before claiming UU/PP/Perpu coverage in the eval.
3. **Penjelasan handling** — for now excluded from the chosen `:Article` text by
   the dedup heuristic; attaching elucidation as a separate field is future work.
4. **Harden `validate_ground_truth.py`** to flag gold IDs whose resolved text is
   trivial/penjelasan, not just missing.

Whether to re-parse vs. migrate `articles.json` + Chroma + Neo4j is open (migration
avoids the ~5h baseline re-embed). Eval-question drafting stays paused until the
corpus is corrected, then resumes — PMK-sourced questions first (clean post-fix),
UU/PP/Perpu only after the ID scheme (2).

## Status of related work

- Eval set: 10 verified (q001–q010); their gold text should be re-checked
  against this issue (they use PP 53/2010, UU 13/2003, PMK 82/2024, PMK 168/2023).
- Question drafting toward 50 is paused pending this fix (TODO §1).
