# Research log

Append-only, dated entries for reproducibility. **Never edit past entries** —
add a new one. Newest at the bottom. For current state see `STATUS.md`; for
decisions and their rationale see `docs/decisions/`.

---

## 2026-05-24 — Parser rewrite, corpus regenerated

- New parser produced `articles.json` + `regulations.json` together (resolving
  the earlier stale-file mismatch).
- Raw articles: 144,329 → 118,966 unique after dedup on
  `(regulation_id, article_number)`. ~6× the previous ~19,400 corpus.

## 2026-05-25 — Full reset + re-ingest, both stores in sync

- `scripts/reset_stores.py` added: idempotent wipe of Chroma + Neo4j
  (batched `DETACH DELETE`, drops the 3 constraints). Flags `--yes`,
  `--chroma`, `--neo4j`.
- Re-ingest run:
  - `ingest-baseline` ~5h (118,966 articles × Ollama embed).
  - `ingest-graph` ~39 min. Ran in parallel with baseline (different services,
    no contention).
- Graph ingest: 107,369 reference edges attempted, **87,088 created**. ~20k
  unresolved targets — dominant cause the OCR `O`→`0` issue; rest are refs to
  articles in regulations not in the JDIH corpus.
- Sanity: `scripts/graph_stats.py` confirms counts (see STATUS.md table). Both
  pipelines smoke-tested on "Apa saja syarat penyaluran DBH Sawit?" — both
  returned coherent Indonesian answers with citations.
  - Baseline: 5 articles, Pasal 22 neighborhood; missed Pasal 16/17 rules.
  - GraphRAG: 36 articles (5 vector seeds + 31 graph-expanded across PMK 10/2026
    and PMK 91/2023); surfaced Pasal 16, 17, 19, 24 via REFERENCES — the exact
    behavior the thesis aims to demonstrate.
- `data/ground_truth/eval.jsonl` seeded with 2 TEMPLATE entries (q001 single,
  q002 multi) anchoring the schema. Gold IDs NOT yet verified against source.

## 2026-06-23 — Project structure cleanup

- Moved Neo4j credentials out of `src/config.py` into gitignored `.env`
  (+ `.env.example`); config now reads from env and raises if unset (ADR 0004).
- Promoted durable facts from `handover.md` into `CLAUDE.md` (env, run commands,
  ID convention, OCR gotcha, working style).
- Split `handover.md` into `STATUS.md` (live state), `TODO.md` (roadmap),
  `docs/building-eval-dataset.md` (playbook), this log, and `docs/decisions/`
  (ADRs). `handover.md` removed.

## 2026-06-24 — Packaging, gitignore hardening, eval drafting

- **Packaging:** added `pyproject.toml` (deps sourced dynamically from
  `requirements.txt`; `requires-python >=3.11`; ruff config) and the missing
  `src/__init__.py` + `src/data_acquisition/__init__.py`. Ran `pip install -e .`
  in the `skripsi` env. `src.*` now imports without `PYTHONPATH=.`; verified
  `python main.py` runs from the project root. CLAUDE.md commands updated to
  drop the prefix.
- **`.gitignore` foot-guns fixed:** scoped the blanket `*.json`/`*.pdf`/`*.html`/
  `*.bin` rules to `data/**` (a top-level `*.json` was silently swallowing
  config/fixture files); corrected stale `data/raw/` → `data/raw_pdfs/`;
  un-ignored `CLAUDE.md` in-repo.
- **AI tooling kept out of git:** moved `CLAUDE.md`, `CLAUDE.local.md`,
  `**/.claude/`, `.cursor/`, `.aider*` into the global ignore
  (`~/.config/git/ignore`) so they're local-only across all repos. Nothing
  AI-related was ever tracked, so no history scrub needed.
- **Tidy:** `jdih_metadata.json` (6 MB) moved to `data/jdih_metadata.json`;
  updated the relative paths in `parser.py` and `jdih_scraper.py`.
- **Ground truth:** `eval.jsonl` grown from 2 templates to 10 drafted questions
  (q001–q010, 6 multi / 4 single), all still `DRAFT` — verification pass not yet
  started. Established the verify convention (notes prefix `DRAFT` vs
  `VERIFIED <date>`) and the rule to re-derive gold from source text to decouple
  it from GraphRAG.
