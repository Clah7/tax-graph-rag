# Context Pack — METHODOLOGY

Authoritative technical facts for writing the thesis methodology chapter.
Grounded in the actual codebase (verified against source, not memory).
If a fact isn't here, ASK — do not invent implementation details.

Last synced from repo: 2026-07-01.

---

## 1. Research design (the comparability keystone)

Two RAG systems are compared:
- **Baseline RAG** = hybrid lexical+dense retrieval.
- **GraphRAG** = the same hybrid seeds + graph expansion over inter-article
  references, re-ranked into the same top-K budget.

Both systems seed through a single dispatch point, `src/seeding.py::seed_search`,
so the seeding stage is IDENTICAL for both. Consequence: any measured performance
difference is attributable to the graph stage ALONE, not to seeding drift. This
"comparable by construction" property is the methodological backbone — reinforce
it wherever relevant.

Framing decision (2026-07-01): "Baseline RAG" in the thesis = hybrid
lexical+dense. Pure-vector (dense-only) seeding is retained as a toggle-off
ABLATION FLOOR (`USE_HYBRID_SEEDING=False`), not the baseline.

---

## 2. Corpus and preprocessing

- **Acquisition:** scraped from JDIH (`src/data_acquisition/jdih_scraper.py`),
  parsed into `articles.json` / `regulations.json` (`parser.py`).
- **Dedup / cleaning** (`src/corpus.py`): 144,329 raw article records →
  **118,966 unique** articles after dedup on the key `(regulation_id,
  article_number)`. Dedup rule: keep the longest non-*penjelasan* (explanatory)
  batang-tubuh text. This fixed ADR 0006 where explanatory text (e.g.
  `"Cukup jelas."`) had wrongly overwritten article bodies (18,255 docs affected,
  re-embedded 2026-06-29).
- **Article ID format:** `"<regulation_id>::<article_number>"`, used identically
  as ChromaDB doc id, Neo4j `:Article.id`, and `gold_article_ids` in eval data.

### Known data issues (report transparently)
- **Omnibus ID collisions** (~1,157 remain): omnibus laws (e.g. UU 7/2021 HPP
  amends KUP/PPh/PPN) reuse Pasal numbers across parent laws. Partially handled;
  remainder logged (ADR 0006).
- **OCR `O`→`0`** (~0.2% of rows, ~287): capital `O` where digit `0` belongs;
  breaks ID matching and poisons REFERENCES edges (~20k of ~107k attempted edges
  didn't resolve). DEFERRED by decision (ADR 0003) due to re-embedding cost.

---

## 3. Dual indexing

- **ChromaDB** collection `tax_articles`: 118,966 article docs, 1024-dim
  embeddings (`qwen3-embedding:0.6b`).
- **Neo4j**: built from the same dedup corpus, verified IN SYNC with ChromaDB
  (gold IDs resolve 13/13; sampled article text byte-identical across stores).

### Graph statistics (as of 2026-06-29 rebuild)
| Element | Count |
|---|---|
| `:Article` | 118,966 |
| `:Regulation` | 5,908 (incl. 549 stubs that are only AMENDS targets) |
| `:Concept` | 9,765 |
| `:BELONGS_TO` | 118,966 |
| `:REFERENCES` | 81,315 (intra + cross regulation) |
| `:AMENDS` | 852 |
| `:DEFINES` | 29,661 |

---

## 4. Graph schema (Neo4j)

Nodes:
- `Regulation` (id, type, title, year)
- `Article` / `Pasal` (id, text, regulation_id)
- `Concept` (name)

Relationships:
- `(Article)-[:BELONGS_TO]->(Regulation)`
- `(Article)-[:REFERENCES]->(Article)`
- `(Article)-[:AMENDS]->(Article)`
- `(Article)-[:DEFINES]->(Concept)`

REFERENCES is the backbone of graph expansion.

---

## 5. Shared seeding stage (`src/seeding.py`, `src/hybrid_search.py`)

`seed_search(query, top_k)` dispatches on `config.USE_HYBRID_SEEDING` (read at
call time, so an ablation driver can flip it in-process).

**Hybrid seeding pipeline** (default; no global BM25 index — only the pool is scored):
1. Dense query for the top-`HYBRID_POOL=200` candidates (ids, text, cosine).
2. BM25 re-rank of those pool docs vs the query. Params k1=1.5, b=0.75; idf over
   the pool. Tokenizer keeps digits (so "Pasal 17", "0,5%" carry signal).
3. Reciprocal Rank Fusion (RRF) of the dense and lexical orderings,
   `HYBRID_RRF_K=60` (standard constant, NOT tuned on eval data).
4. Return the fused top-k.

Rationale (diagnosis 2026-07-01): the 0.6b embedder recalls the right article
into a deep pool but ranks it below the top-5 cutoff; lexical signal anchors the
cited terms ("Pajak Hotel", regulation names) the dense model smears.

Returned article dict includes: `score` (dense cosine, carried for graph-boost
math), `fused_score` (RRF), `source="hybrid"`.

---

## 6. System 1 — Baseline RAG (hybrid)

`seed_search` (hybrid) → assemble top-5 context → generate with `qwen3.5:9b`.
This is a STRONG baseline (not deliberately weakened), so the comparison against
GraphRAG is conservative.

---

## 7. System 2 — GraphRAG (`src/graph_rag/retriever.py`)

Three stages:
1. **Seed**: identical `seed_search`.
2. **Graph expansion** (`_graph_expand`): from seeds, follow `REFERENCES` edges
   up to `GRAPH_HOP_DEPTH=2` hops (Cypher variable-length path). For each reached
   article, track: which seeds reach it, shortest hop per seed, and the article's
   REFERENCES degree.
3. **Strict-parity re-rank** to the same budget (`GRAPH_CONTEXT_BUDGET ==
   TOP_K_VECTOR = 5`), so a linked neighbor can only enter context by out-scoring
   a weak seed.

Scoring:
```
score(x) = query_sim(x) + alpha * boost(x)
boost(x) = ( Σ over seeds s reaching x of sim(s)/hop(s,x) ) / (1 + log(1 + degree(x)))
```
- **Symmetric**: seeds are boosted too (a seed reached from other seeds earns
  boost), so a relevant gold seed isn't unfairly displaced.
- **Degree-damped** (`/(1+log(1+degree))`): amendment hubs (e.g. UU 1/2022) earn
  little boost per link, fixing the naive alpha=0.5 regression (test MRR
  0.41→0.19) where hubs displaced gold seeds.
- `alpha=0` reproduces baseline exactly.
- `GRAPH_RERANK_ALPHA=0.10` (tuned on the HYBRID dev split; 0.15 on pure-dense).
  ALPHA IS TUNED ON THE DEV SPLIT ONLY, never on test.

Implementation note: `gather()` does all alpha-independent I/O (embed, seed,
graph, neighbor embeddings); `rerank()` is pure-Python and alpha-dependent, so
`scripts/tune_alpha.py` can sweep alpha over cached candidates.

---

## 8. Evaluation design

- **Ground truth** `data/ground_truth/eval.jsonl`: 50 VERIFIED entries (29
  multi-hop, 21 single-hop; 13 cross-regulation multi-hops) — at target 50. Each
  row `{id, question, gold_article_ids, gold_answer, hop_type, notes}`, grounded
  verbatim in source text, hand-verified (78 unique gold IDs, all resolve as both
  Neo4j `:Article` and ChromaDB docs; gold resolves to the batang tubuh, not the
  penjelasan collisions in `articles.json` — ADR 0006). Topics: cukai/kepabeanan,
  disiplin PNS, ketenagakerjaan, PPh 21 (incl. TER PP 58/2023 ↔ PMK 168/2023),
  natura/kenikmatan (UU HPP ↔ PP 55/2022), Bea Materai, PPh final UMKM, PPh 22
  pemungutan (UU 7/1983 ↔ PMK), fasilitas PPh penanaman modal, PDRD (UU 28/2009).
- **Frozen split BEFORE tuning** (ADR 0002): `scripts/make_split.py`, stratified
  by hop_type, seed 20260701 → **dev=8** (3 single, 5 multi), **test=16** (5
  single, 11 multi). Tune on dev, report on test.
- **Metrics:** recall@5, hit@5, MRR. RAGAS (generation-side) DEFERRED (dep
  conflict + plan to use a judge model other than the generator to avoid
  self-judge bias; answers are cached so it's cheap to add later).
- **Harness** (`eval run --hybrid/--alpha/--split`): runs `dense_test` +
  `hyb_test`, paired stats (Wilcoxon / paired-t). Each run row stamped
  `meta={seeding, alpha, split}`.

---

## 9. Implementation environment

- Python; ChromaDB; Neo4j (official driver, Cypher).
- Ollama: `qwen3.5:9b` (LLM, `num_ctx`=16384), `qwen3-embedding:0.6b` (1024-dim).
- Neo4j credentials via `.env` (ADR 0004), never committed.
- Retrieval config: `TOP_K_VECTOR=5`, `GRAPH_HOP_DEPTH=2`.
