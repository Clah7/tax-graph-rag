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

`data/ground_truth/eval.jsonl` — **24 entries (q001–q024), all `VERIFIED`.**
Composition: 16 multi-hop (q001–q006, q011–q012, q015–q022), 8 single-hop
(q007–q010, q013–q014, q023–q024). Target: 50 verified. All 36 unique gold IDs
resolve in both stores, 0 penjelasan/trivial (`scripts.validate_ground_truth`).

Topic spread: cukai (PMK 82/2024) ×2, disiplin PNS (PP 53/2010) ×3,
ketenagakerjaan (UU 13/2003) ×3, PPh 21 (PMK 168/2023) ×2, Bea Materai
(UU 10/2020) ×4 (q011–q014), PPh final UMKM (PP 23/2018 ↔ PMK 99/2018) ×4
(q015–q018), PDRD (UU 28/2009: BPHTB, Pajak Hotel, PKB, jenis pajak provinsi,
objek BPHTB, muatan Perda) ×6 (new, q019–q024). Skew toward non-tax topics from
the first batch is being corrected — recent batches lean tax.

**q011–q014 authored + verified 2026-06-29** from UU 10/2020 (Bea Materai),
grounded verbatim in source text and hand-verified against it.

**q015–q018 authored + verified 2026-06-29** — first **cross-regulation**
multi-hop batch: each answer needs one PP 23/2018 article (norm: tarif 0,5%,
ambang Rp4,8M, DPP, opsi KUP) + one PMK 99/PMK.03/2018 article (pelaksana:
pelunasan, angsuran PPh 25, tata cara pemberitahuan, penyetoran). Genuine
inter-regulation REFERENCES / delegation edges — the case GraphRAG should win.
Grounded verbatim; hand-verified. Note: PP 23/2018 is revoked by PP 55/2022, but
the 0,5% rate / Rp4,8M threshold were carried forward unchanged, so not a
superseded-content trap; flagged in each row's `notes`.

**q019–q024 authored + verified 2026-06-29** from UU 28/2009 (PDRD), grounded
verbatim in source text (corpus `data/processed/articles.json`). Four
computation-chain multi-hops (q019 BPHTB, q020 Pajak Hotel, q021 PKB tarif+DPP,
q022 jenis pajak provinsi + bagi hasil), each chaining tarif / dasar pengenaan /
rumus penghitungan across 2–3 same-regulation articles via explicit REFERENCES
edges; two single-hop controls (q023 objek BPHTB, q024 muatan minimal Perda).

**Sourcing finding (methodology):** the amendment-law tax UUs (UU 36/2008 PPh,
UU 42/2009 PPN, UU 28/2007 KUP) are poor gold sources as stored — their text
carries amendment framing ("Ketentuan Pasal X diubah…") and **superseded rates**
(PPh badan 28/25%, PPN 10%, KUP flat 2%/bln — all changed by UU 7/2021 HPP).
Prefer clean + current sources (UU 10/2020 Bea Materai, self-contained PMKs, or a
verified consolidated law) when authoring tax questions; record rejections.
Coretax chains (PER-7/PJ/2025 ↔ PMK 81/2024) were rejected for q015–q018: the
linked article pairs restate the same rule (redundant), so they fail the "must
use both regs" test for multi-hop.

**Verification passes complete** — q001–q010 (2026-06-28), q011–q024
(2026-06-29); verified by hand against PMK/PP/UU source text, each `notes` starts
with `VERIFIED`. Procedure: `docs/building-eval-dataset.md`.

## Retrieval & evaluation (2026-07-01)

**Dev/test split frozen** before tuning (ADR 0002): `data/ground_truth/split.json`
(`scripts.make_split`, stratified by hop_type, seed 20260701) — **dev = 8** (3
single, 5 multi), **test = 16** (5 single, 11 multi). Tune on dev, report on test.

**First full comparison (run v24, dense seeds, 24 q).** With the original
append-only graph retriever, baseline and graph are **identical at top-5 by
construction** (graph seeds from the same top-5 vectors, then appends neighbors at
rank 6+). Graph only diverged at deep k (recall@20 +0.13, p=0.03) bought with
precision collapse and 147-article / 193s contexts that hit Ollama's 300s timeout.

**Strict-parity re-ranker** (commit `1005e85`, `src/graph_rag/retriever.py`):
seeds + graph neighbors scored `sim + alpha*boost` and truncated to the same
TOP_K=5 budget, so a linked neighbor can only enter by out-scoring a weak seed.
`boost` is symmetric (seeds boosted too) and **degree-damped** (`/(1+log(1+deg))`)
so amendment hubs (UU 1/2022, UU 18/~1997) stop displacing gold seeds — the bug
that made the naive alpha=0.5 version collapse (test mrr 0.41→0.19). Truncation
fixed the latency/timeout/precision problems. `gather()` (I/O) is split from
`rerank()` (pure-python) so `scripts.tune_alpha` sweeps alpha over cached
candidates retrieval-only. **Result: dev picked alpha=0.15 (recall@5 .375→.500)
but it is a WASH on held-out test** (recall@5 .469→.469, hit@5 .625→.563, mrr
.424→.440). Dev gain was n=8 noise. → **Null result on retrieval IR; ranking is
not the bottleneck.**

**Seeding diagnosis (the real bottleneck).** Gold is mis-ranked, not missing:
**41/44 gold IDs are within the dense top-200**, just buried below the top-5
cutoff (e.g. Pasal 156 @174, Pasal 2 @56, Pasal 87 @64, Pasal 3 @48). The 0.6b
embedding model recalls them but ranks them poorly; only 3/44 are truly absent.

**Hybrid lexical+dense seeding (prototype, measured retrieval-only).** Dense
top-200 pool ⊕ BM25 re-rank of the pool, fused by RRF (k=60, standard default —
no tuning). **Generalizes to held-out test**, unlike the graph re-rank:

| metric | dense-only | hybrid (RRF) | test delta |
|---|---|---|---|
| recall@5 | 0.469 | 0.521 | +0.052 |
| hit@5 | 0.625 | 0.750 | +0.125 |
| mrr | 0.424 | 0.547 | +0.123 |

Lexical signal anchors the cited terms ("Pajak Hotel", regulation names) the
dense model smears.

**Wired in** (commit `69e8c99`): `src/hybrid_search.py` + `src/seeding.py`
dispatch (`USE_HYBRID_SEEDING` toggle, default off so the pure-vector baseline is
preserved), shared by both pipelines. **The 2×2 on held-out test** (alpha
re-tuned on dev only, hybrid dev-best = 0.10):

| system | recall@5 | hit@5 | mrr |
|---|---|---|---|
| dense-baseline | 0.469 | 0.625 | 0.424 |
| hybrid-baseline | 0.521 | 0.750 | 0.547 |
| dense + graph (α=0.15) | 0.469 | 0.563 | 0.440 |
| **hybrid + graph (α=0.10)** | **0.698** | **0.938** | 0.477 |

**Key finding: graph expansion is null on dense seeds but decisive on hybrid
seeds** — recall@5 0.521→0.698, hit@5 0.750→0.938 (gold reaches the LLM for 15/16
test questions). The graph win only materializes once seeds land in the right
regulation, so its expansion can follow the cross-reg REFERENCES edge. End-to-end
dense-baseline → hybrid+graph: recall@5 +0.23 (+49% rel), hit@5 +0.31. Trade-off:
mrr dips (first gold slips to rank 2–3) — immaterial for context-filling.

**Harness 2×2 with paired stats** (commit `17ec12a` added `eval run
--hybrid/--alpha/--split`; runs `dense_test` + `hyb_test`, test split n=16).
Confirms the retrieval-only numbers with Wilcoxon/paired-t: on hybrid seeds graph
lifts **recall@5 0.521→0.698 (Wilcoxon p=0.026, 6 wins / 0 losses)**, hit@5
0.750→0.938 (p=0.083); on dense seeds graph is null (recall@5 p=1.0). mrr dip
−0.07 (ns). Each run row is stamped with `meta={seeding,alpha,split}`.

**RAGAS (generation-side) deferred** — the env's `ragas` (0.4.3 metadata but
0.1.x-style `vertexai` import) fails against `langchain-community 0.4.2`, and
`ragas_metrics.py` targets the old 0.1.x API. Answers are cached in the run files,
so RAGAS is cheap to add later once deps are pinned — ideally with a judge model
other than the generator (`qwen3.5:9b`) to avoid self-judge bias.

**Framing decided (2026-07-01): hybrid is the shared baseline.** "Baseline RAG"
in the thesis = hybrid lexical+dense; GraphRAG builds on the same seeds, isolating
the graph stage. `USE_HYBRID_SEEDING` now defaults ON and `GRAPH_RERANK_ALPHA`
defaults to the hybrid-tuned 0.10; pure-vector is the toggle-off ablation floor
(run without `--hybrid`). Headline comparison is therefore the `hyb_test` cell:
graph recall@5 0.698 vs baseline 0.521 (Wilcoxon p=0.026). Still open: larger
eval set (n=16 test underpowered).
