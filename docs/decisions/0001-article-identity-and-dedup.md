# 0001 — Article identity and dedup key

- **Status:** Accepted
- **Date:** 2026-05-24

## Context

The corpus has many regulations, each with numbered articles (Pasal). The same
article must be addressable identically across ChromaDB (vector store), Neo4j
(graph), and the ground-truth eval set, otherwise retrieval results can't be
joined to gold labels. Raw parsing yields duplicates (144,329 raw rows) because
the same Pasal appears multiple times in source documents.

## Decision

- An article's identity is the pair `(regulation_id, article_number)`.
- Its canonical string id is `"<regulation_id>::<article_number>"`, used
  verbatim as the ChromaDB doc id, Neo4j `:Article.id`, and every
  `gold_article_ids` entry in `eval.jsonl`.
- Dedup the raw corpus on that pair → 118,966 unique articles.

## Consequences

- Metrics joins (retrieved IDs vs gold IDs) are exact string matches — simple
  and unambiguous.
- The identity is only as clean as `article_number`. The OCR `O`→`0` corruption
  (ADR 0003) directly breaks identity: `1O` and `10` become distinct articles,
  causing dedup misses and unmatchable gold IDs.
- Any future change to the id format must be migrated across all three stores
  *and* the eval set simultaneously.
