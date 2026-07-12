# Context Pack — GLOSSARY

Fixed terminology for consistent thesis writing. Use these exact terms; do not
introduce synonyms mid-document. Bahasa Indonesia is the writing language;
English technical terms are kept where they are standard.

Last synced from repo: 2026-07-07.

---

## Core system terms

| Term (canonical) | Meaning / usage |
|---|---|
| **Baseline RAG** | The hybrid lexical+dense system. In this thesis "Baseline RAG" = hybrid, NOT pure-dense. Bahasa: *Baseline RAG (hibrida)*. |
| **GraphRAG** | Same hybrid seeds + graph expansion over REFERENCES, re-ranked into the same top-K. Keep as "GraphRAG". |
| **seeding / tahap seeding** | Stage-1 seed retrieval, shared by both systems via `src/seeding.py`. Bahasa: *tahap seeding* / *tahap penyemaian*. Prefer "seeding". |
| **hybrid seeding / seeding hibrida** | Dense top-200 pool ⊕ BM25 re-rank of the pool, fused by RRF. |
| **pure-vector / dense-only** | Dense-only seeding; the ABLATION FLOOR (toggle-off), not the baseline. Bahasa: *dense murni*. |
| **graph expansion / ekspansi graf** | Following REFERENCES edges up to GRAPH_HOP_DEPTH hops from seeds. Bahasa: *perluasan graf* / *ekspansi graf* (pick one and keep it). |
| **strict-parity re-rank** | Re-ranking seeds + neighbors into the same TOP_K budget. Bahasa: *re-rank paritas-ketat* / *pemeringkatan-ulang paritas-ketat*. |
| **ablation floor** | The toggle-off pure-vector configuration used as a comparison floor. Bahasa: *lantai ablasi*. |

## Retrieval / IR terms

| Term | Meaning / usage |
|---|---|
| **dense retrieval** | Embedding-based semantic retrieval (ChromaDB). Bahasa: *temu-kembali dense*. |
| **lexical / BM25** | Keyword-based scoring (BM25, k1=1.5, b=0.75). Bahasa: *temu-kembali leksikal*. |
| **RRF (Reciprocal Rank Fusion)** | Rank-fusion of dense + lexical orderings, k=60. Keep "RRF". |
| **seed** | A stage-1 retrieved article. Bahasa: *seed* (pertahankan istilah). |
| **neighbor / tetangga** | An article reached via graph expansion. Bahasa: *tetangga (tertaut)*. |
| **hop / hop_type** | Reference-edge distance; question class (single-hop / multi-hop). Bahasa: *single-hop* / *multi-hop* (pertahankan). |
| **degree damping / hub damping** | Down-weighting high-degree hub nodes in the boost. Bahasa: *peredaman derajat* / *hub damping*. |
| **recall@k, hit@k, MRR** | Evaluation metrics. Keep symbols; define once. |

## Domain (tax) terms — keep Indonesian

| Term | Note |
|---|---|
| **Pasal** | Article. Node label is `Article`/`Pasal`. Use "Pasal" in prose. |
| **keterkaitan antar pasal** | Inter-article dependency — the phenomenon GraphRAG targets. |
| **batang tubuh** | The operative body text of an article (vs *penjelasan*). |
| **penjelasan** | Explanatory notes; excluded/deprioritized in dedup. |
| **omnibus** | Laws reusing Pasal numbers across parent regulations (e.g. UU 7/2021 HPP). |
| Regulation types | UU (Undang-Undang), PP (Peraturan Pemerintah), PMK (Peraturan Menteri Keuangan), Perpu, PER. Keep abbreviations consistent. |

## Systems / tools

| Term | Note |
|---|---|
| **ChromaDB** | Vector store, collection `tax_articles`. |
| **Neo4j** | Graph database; queried with Cypher. |
| **Ollama** | Local LLM/embedding server. |
| **qwen3.5:9b** | Generation LLM (num_ctx 16384). |
| **qwen3-embedding:0.6b** | Embedding model, 1024 dimensions. |

## Identifiers

| Term | Note |
|---|---|
| **Article ID** | Format `"<regulation_id>::<article_number>"`, identical across ChromaDB, Neo4j, and gold IDs. |
| **gold_article_ids** | Hand-labeled correct articles for an eval question. |
| **dev / test split** | dev=17, test=33, frozen before tuning (ADR 0007, seed 20260701, stratified by hop_type). Tune on dev, report on test. |
