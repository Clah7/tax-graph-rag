# Status

Current state of the project. **Overwrite this file freely** — it reflects
"where things stand now," not history. For dated history see
`docs/research-log.md`; for the roadmap see `TODO.md`.

## Stores (last verified 2026-05-25)

Both stores wiped and rebuilt from the parser's `articles.json` /
`regulations.json`; in sync and queryable.

| Store | Count |
|---|---|
| ChromaDB `tax_articles` | 118,966 article docs (1024-dim qwen3 embeddings) |
| Neo4j `:Article` | 118,966 |
| Neo4j `:Regulation` | 5,908 (incl. 549 stubs that are only AMENDS targets) |
| Neo4j `:Concept` | 10,050 |
| `:BELONGS_TO` | 118,966 |
| `:REFERENCES` | 87,088 (intra + cross) |
| `:AMENDS` | 852 |
| `:DEFINES` | 30,689 |

Raw articles on disk: 144,329 → 118,966 unique after dedup on
`(regulation_id, article_number)` (~6× the pre-rewrite corpus of ~19,400).

## Open issues

- **Article-ID collisions** (new 2026-06-29; see ADR 0006). The identity key
  `(regulation_id, article_number)` collapses distinct provisions: omnibus laws
  (UU 7/2021 HPP amends KUP/PPh/PPN) reuse Pasal numbers, and Penjelasan is
  captured under the same number as its batang tubuh. ~19,246 (16.2%) of groups
  have >1 raw record; **~6,031 (~5%) merge ≥2 genuinely distinct bodies**. Dedup
  keeps the *last* record arbitrarily (Chroma `seen[id]=a`; Neo4j `ON MATCH SET
  a.text`), so survivors can be wrong-law text or a `"Cukup jelas."` stub (e.g.
  `UU 7/2021::9`). Blocks eval sourcing from affected laws and degrades both RAG
  corpora. Eval drafting paused pending fix.
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

`data/ground_truth/eval.jsonl` — **10 entries (q001–q010), all `VERIFIED`.**
Composition so far: 6 multi-hop (q001–q006), 4 single-hop (q007–q010). Target:
50 verified.

**Verification pass complete (2026-06-28).** All 10 rows verified by hand
against the PMK/PP/UU source text; each `notes` now starts with `VERIFIED`.
13 unique gold IDs all resolve in both ChromaDB and Neo4j
(`python -m scripts.validate_ground_truth`) — no missing IDs, no OCR `O`→`0`
suspects.

Next: author toward 50 (keep ~60% multi / ~40% single, spread across
PMK/PP/UU/Perpu/Perpres, no topic >~20%), then freeze a 30% held-out test split
before tuning. Several early rows (q008–q010) self-flagged an incomplete
`gold_answer` during drafting — re-confirm those were tightened during the
verification pass. Procedure: `docs/building-eval-dataset.md`.
