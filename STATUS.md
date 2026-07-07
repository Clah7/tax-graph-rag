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

`data/ground_truth/eval.jsonl` — **50 entries, all `VERIFIED` (q001–q050)** — at
target. Composition: **29 multi-hop / 21 single-hop; 13 cross-regulation
multi-hops**. 78 unique gold IDs, all resolve as both Neo4j `:Article` and ChromaDB
docs (gold = batang tubuh, not the `articles.json` penjelasan collisions; ADR 0006).
Procedure: `docs/building-eval-dataset.md`; adjudication log in
`docs/research-log.md` (2026-07-05).

**q032–q050 (VERIFIED 2026-07-05)** — 19 new rows, cross-reg-first: PPh 22
pemungutan (UU 7/1983 ↔ PMK), cukai/kepabeanan delegations, biaya jabatan, natura
(UU HPP ↔ PP 55/2022), PPh 21 TER (PP 58/2023 ↔ PMK 168/2023), fasilitas penanaman
modal, UMKM final, KUP SPT denda, plus single-hop controls. Authored bottom-up from
REFERENCES hubs + top-down for current-law pairs; each gold read against source text.
**q035 reclassified multi→single (2026-07-05):** its PMK gold (39/PMK.04/2006) was
revoked with no successor mapping and `UU 10/1995::7` ayat (3) already carries the
sanction + amount (skippable) → gold = `UU 10 TAHUN 1995::7`.

### Ground-truth composition (achieved @ 50)

| Dimension | Target @ 50 | Achieved @ 50 |
|---|---|---|
| multi / single | 30 / 20 (60/40) | **29 / 21 (58/42)** |
| cross-reg multi | ~13 | **13** |
| max per regulation | ≤10 (20%) | ≤10 (UU 28/2009 frozen at 6) |

29/21 rather than 30/20 because **q035 was reclassified multi→single** during
pre-freeze gold adjudication — a defensibility fix, not a shortfall.

**Split re-frozen at 50 (ADR 0007):** fresh stratified split (seed 20260701,
dev_frac 0.34) → **dev 17 / test 33** (8 cross-reg multi in test). Sound despite
ADR 0002 because **alpha is frozen** (0.10 hybrid / 0.15 dense) and NOT re-tuned
after the re-split. Supersedes the old q001–q024 dev=8/test=16 split.

**Stats note:** benchmark eval sets are far larger (HotpotQA subset 1,000;
MultiHop-RAG 2,556) but auto-generated; n=50 hand-verified trades scale for
defensibility. Credibility therefore rests on paired stats + construction rigor,
not scale — report **Wilcoxon p + paired bootstrap 95% CI** and state the
n-underpowered caveat explicitly. Graph-construction recall (~20k unresolved
REFERENCES edges from OCR) is an upper bound on achievable graph recall — name it
when framing a modest/null cell.

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

**Dev/test split frozen** (ADR 0002; re-frozen at n=50 per ADR 0007):
`data/ground_truth/split.json` (`scripts.make_split`, stratified by hop_type,
seed 20260701) — **dev = 17** (7 single, 10 multi), **test = 33** (14 single,
19 multi; 8 cross-reg multi). Alpha frozen — not re-tuned after the re-split.

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

**Hybrid lexical+dense seeding (n=16 prototype, retrieval-only; current v50 2×2
is below).** Dense top-200 pool ⊕ BM25 re-rank of the pool, fused by RRF (k=60,
standard default — no tuning). **Generalizes to held-out test**, unlike the graph
re-rank:

| metric | dense-only | hybrid (RRF) | test delta |
|---|---|---|---|
| recall@5 | 0.469 | 0.521 | +0.052 |
| hit@5 | 0.625 | 0.750 | +0.125 |
| mrr | 0.424 | 0.547 | +0.123 |

Lexical signal anchors the cited terms ("Pajak Hotel", regulation names) the
dense model smears.

**Wired in** (commit `69e8c99`): `src/hybrid_search.py` + `src/seeding.py`
dispatch (`USE_HYBRID_SEEDING` toggle, default off so the pure-vector baseline is
preserved), shared by both pipelines. **The 2×2 on the held-out test — v50,
test n=33** (ADR 0007 split; alpha frozen, NOT re-tuned; runs `hyb_test_v50` /
`dense_test_v50`, paired bootstrap 95% CIs):

| system | recall@5 | hit@5 | mrr |
|---|---|---|---|
| dense-baseline | 0.470 | 0.606 | 0.437 |
| hybrid-baseline | 0.571 | 0.758 | 0.452 |
| dense + graph (α=0.15) | 0.490 | 0.576 | 0.443 |
| **hybrid + graph (α=0.10)** | **0.677** | **0.848** | 0.503 |

**Key finding holds: graph expansion is null on dense seeds, decisive on hybrid
seeds.** Headline (hybrid baseline → hybrid+graph): **recall@5 0.571→0.677,
Δ=+0.106, 95% CI [+0.020,+0.202], Wilcoxon p=0.044, 7 wins / 1 loss**; precision@5
also significant (Δ=+0.042, p=0.035); hit@5 0.758→0.848 (p=0.18). Dense seeds:
graph null (recall@5 Δ=+0.020, p=0.55). Multi-hop slice: recall@5 Δ=+0.132 (CI
[+0.009,+0.263]) but Wilcoxon marginal (p=0.079, n=19); single-hop controls barely
move (+0.071, ns). vs the old n=16: effect moderated (Δ 0.177→0.106; p 0.026→0.044)
— larger n, proper CI, still significant. Each run row is stamped with
`meta={seeding,alpha,split}`. Full table + caveats: `docs/context-packs/RESULTS.md` §0.

**RAGAS (generation-side) deferred** — the env's `ragas` (0.4.3 metadata but
0.1.x-style `vertexai` import) fails against `langchain-community 0.4.2`, and
`ragas_metrics.py` targets the old 0.1.x API. Answers are cached in the run files,
so RAGAS is cheap to add later once deps are pinned — ideally with a judge model
other than the generator (`qwen3.5:9b`) to avoid self-judge bias.

**Framing decided (2026-07-01): hybrid is the shared baseline.** "Baseline RAG"
in the thesis = hybrid lexical+dense; GraphRAG builds on the same seeds, isolating
the graph stage. `USE_HYBRID_SEEDING` now defaults ON and `GRAPH_RERANK_ALPHA`
defaults to the hybrid-tuned 0.10; pure-vector is the toggle-off ablation floor
(run without `--hybrid`). Headline comparison is therefore the `hyb_test_v50` cell:
graph recall@5 0.677 vs baseline 0.571 (Wilcoxon p=0.044, 95% CI [+0.020,+0.202]).
Eval set now frozen at 50 (test n=33); still open: RAGAS generation-side eval.

## Thesis writing (2026-07-02)

Writing surface decided: **Google Docs** for the manuscript (Universitas
Padjadjaran format), with a **Claude.ai Project** as the drafting assistant. To
keep the LLM grounded, repo-derived **context packs** live in
`docs/context-packs/` (`METHODOLOGY.md`, `RESULTS.md`, `GLOSSARY.md`) — uploaded
as Project Knowledge. **`RESULTS.md` must be re-synced whenever the eval numbers
change** (a static snapshot; current numbers are the v50 test n=33 headline, §0).
A LaTeX scaffold under `thesis/` (Unpad template, `Header/` + `Isi/`) exists but
is **untracked** and secondary to the Docs workflow. Citation discipline: context
packs contain **no citations**; the literature review is authored by hand to
avoid fabricated references.
