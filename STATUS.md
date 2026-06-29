# Status

Current state of the project. **Overwrite this file freely** — it reflects
"where things stand now," not history. For dated history see
`docs/research-log.md`; for the roadmap see `TODO.md`.

## Stores (Neo4j rebuilt + verified in sync 2026-06-29)

Built from the parser's `articles.json` / `regulations.json`. **Both stores are
now IN SYNC on the corrected batang-tubuh text** — eval comparisons are
unblocked. ChromaDB was migrated 2026-06-29 (ADR 0006 dedup fix, 18,255 docs
re-embedded); Neo4j was wiped (`reset_stores --neo4j`) and rebuilt 2026-06-29
from the same corrected dedup corpus (`src/corpus.load_articles`: 144,329 →
118,966, 1,157 omnibus collisions logged), refreshing article text and
`REFERENCES`/`DEFINES` edges. Verified post-rebuild: gold IDs resolve 13/13 in
both stores; sampled gold article text is byte-identical Chroma vs Neo4j. Edge
counts dropped from the pre-rebuild snapshot (corrected text extracts fewer
references/definitions) — expected.

| Store | Count |
|---|---|
| ChromaDB `tax_articles` | 118,966 article docs (1024-dim qwen3 embeddings) |
| Neo4j `:Article` | 118,966 |
| Neo4j `:Regulation` | 5,908 (incl. 549 stubs that are only AMENDS targets) |
| Neo4j `:Concept` | 9,765 |
| `:BELONGS_TO` | 118,966 |
| `:REFERENCES` | 81,315 (intra + cross) |
| `:AMENDS` | 852 |
| `:DEFINES` | 29,661 |

Raw articles on disk: 144,329 → 118,966 unique after dedup on
`(regulation_id, article_number)` (~6× the pre-rewrite corpus of ~19,400).

## Open issues

- **Article-ID collisions** (new 2026-06-29; see ADR 0006). The identity key
  `(regulation_id, article_number)` collapses distinct provisions: omnibus laws
  (UU 7/2021 HPP amends KUP/PPh/PPN) reuse Pasal numbers, and Penjelasan is
  captured under the same number as its batang tubuh. ~19,246 (16.2%) of groups
  have >1 raw record; the old dedup kept the *last* record arbitrarily, so 18,255
  articles held wrong/penjelasan text (e.g. `UU 7/2021::9` = `"Cukup jelas."`).
  **Fixed in ingestion** via shared `src/corpus.py` (longest non-penjelasan).
  **ChromaDB migrated 2026-06-29** (`scripts/migrate_dedup_text`, 18,255 docs
  re-embedded; idempotency + gold-ID validation pass). **Neo4j rebuilt
  2026-06-29** — wiped + re-ingested from the corrected dedup corpus (correct
  text AND edges; ~38 min); verified in sync with ChromaDB (gold IDs 13/13,
  sampled text byte-identical). ~1,157 true omnibus collisions remain (UU/PP/
  Perpu) pending the ID scheme (ADR 0006 item 2).
- **OCR `O`→`0`** (not fixed; deferred by decision — see ADR 0003). ~287 rows
  (~0.2%) have capital `O` where digit `0` belongs. Breaks dedup and poisons
  `REFERENCES` edges (~20k of 107k attempted edges didn't resolve to a target
  `:Article`). Fix options: (a) normalise in `parser.py` + re-ingest;
  (b) migration script over `articles.json` + Chroma + Neo4j (saves ~5h embed).
- **Cartesian-product warning** in `src/graph_rag/ingestion.py`
  `_ingest_definitions` (`MATCH (a), (c) MERGE ...`). Build completes but the
  DEFINES phase is slow (~4 min). Refactor to `UNWIND $rows ... MATCH ... MERGE`.
  Not blocking.

## Ground truth

`data/ground_truth/eval.jsonl` — **14 entries (q001–q014), all `VERIFIED`.**
Composition: 8 multi-hop (q001–q006, q011–q012), 6 single-hop (q007–q010,
q013–q014). Target: 50 verified. All 17 unique gold IDs resolve in both stores,
0 penjelasan/trivial (`scripts.validate_ground_truth`).

Topic spread: cukai (PMK 82/2024) ×2, disiplin PNS (PP 53/2010) ×3,
ketenagakerjaan (UU 13/2003) ×3, PPh 21 (PMK 168/2023) ×2, Bea Materai
(UU 10/2020) ×4 (new, q011–q014). Skew toward non-tax topics from the first
batch is being corrected — next batches lean tax.

**q011–q014 authored + verified 2026-06-29** from UU 10/2020 (Bea Materai),
grounded verbatim in source text and hand-verified against it.

**Sourcing finding (methodology):** the amendment-law tax UUs (UU 36/2008 PPh,
UU 42/2009 PPN, UU 28/2007 KUP) are poor gold sources as stored — their text
carries amendment framing ("Ketentuan Pasal X diubah…") and **superseded rates**
(PPh badan 28/25%, PPN 10%, KUP flat 2%/bln — all changed by UU 7/2021 HPP).
Prefer clean + current sources (UU 10/2020 Bea Materai, self-contained PMKs, or a
verified consolidated law) when authoring tax questions; record rejections.

**Verification passes complete** — q001–q010 (2026-06-28), q011–q014
(2026-06-29); verified by hand against PMK/PP/UU source text, each `notes` starts
with `VERIFIED`. Procedure: `docs/building-eval-dataset.md`.
