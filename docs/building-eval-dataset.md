# Building the evaluation dataset

Procedural guide for growing `data/ground_truth/eval.jsonl` from the template
entries to ~50 verified questions. Stable reference — update when the procedure
changes, not per session. Current progress lives in `STATUS.md` / `TODO.md`.

## 0. Pre-work: tools at hand

- **Schema** (`src/evaluation/dataset.py`): each line is
  `{id, question, gold_article_ids, gold_answer, hop_type, notes}`.
  `gold_article_ids` use `"<regulation_id>::<article_number>"` exactly as stored
  in ChromaDB/Neo4j.
- **Corpus lookup:** `data/processed/articles.json` is the source of truth for
  IDs and text. Open once and grep — faster than spinning up the pipelines.
- **Target composition:** 50 questions, ~30 multi-hop, ~20 single-hop, spread
  across PMK/PP/UU/Perpu/Perpres, no single topic > ~20% (≤10 questions).

## 1. Pick a sourcing strategy per question

Mix two approaches. Tag each in `notes` so the methodology section can describe
the sourcing distribution. Aim ~70/30 bottom-up/top-down.

**(a) Bottom-up (graph-anchored) — best for multi-hop.**
1. From `scripts/graph_stats.py`, get top-N articles by incoming `REFERENCES`
   degree (e.g. `234/PMK.01/2015::1`, 216 incoming refs).
2. Pick one. Open it in `articles.json`. Read its text + 2–4 articles that
   reference it via Neo4j:
   `MATCH (a:Article)-[:REFERENCES]->(t:Article {id:$id}) RETURN a.id, a.text`.
3. Compose a question whose answer *requires* synthesizing across the hub + at
   least one neighbor. If the hub alone answers it, file it under single-hop.
4. Gold IDs = the hub + every neighbor actually used to write `gold_answer`. Be
   strict: if Pasal 17 is cited in the answer, it must be in `gold_article_ids`.

**(b) Top-down (authentic-question) — best for realism.**
1. Collect raw questions: DJP FAQ (`pajak.go.id`), Ortax forums, KSAP, prior
   tax-law thesis question banks, supervisor's exam questions.
2. For each, grep `articles.json` keywords to find the answering Pasal(s).
3. Reject any question whose answering Pasal isn't in the corpus — don't
   paraphrase to fit. Note rejections; useful in the limitations section.

## 2. Per-question workflow (~15 min each)

1. **Draft the question in Indonesian.** Natural phrasing, not template-y.
   Don't copy Pasal text into the question — it leaks the answer to the retriever.
2. **Find gold Pasal(s).** Search `articles.json` by keyword; open each
   candidate's full text. Confirm by *reading*, not by trusting vector similarity.
3. **Write `gold_answer` in Indonesian**, ~2–5 sentences, grounded only in the
   gold Pasal(s). Cite each inline ("…sebagaimana Pasal 17 ayat (1)…"). This is
   the LLM-as-judge reference, so keep it tight.
4. **Set `hop_type`.** `single` only if one Pasal contains the full answer;
   `multi` if it requires combining ≥2 distinct Pasal. Several ayat in *one*
   Pasal is still `single`.
5. **Write `notes`.** Include: (i) sourcing strategy (a/b), (ii) why multi-hop
   if marked so, (iii) any ambiguity resolved. Defense-prep ammunition.
6. **Assign `id`** as `q003`, `q004`, … incrementing. Don't reuse IDs even if a
   question is deleted — gaps are fine; ID stability matters for run joins.

## 3. Validation script (write after question 5)

Write `scripts/validate_ground_truth.py`. Minimal checks:

- Each `id` unique and matches `^q\d{3}$`.
- Each `gold_article_ids` entry non-empty and `::`-delimited.
- For every gold ID: (a) exists as a ChromaDB doc (`collection.get(ids=[...])`),
  and (b) exists as a Neo4j `:Article` node (`MATCH (a:Article {id:$id}) RETURN a`).
- `hop_type == "single"` ⇒ `len(gold_article_ids) == 1` (warn, don't fail).
- `gold_answer` non-empty for any question Ragas should score.

Run on every save. Catches the OCR `O`→`0` bug that silently makes gold IDs
unmatchable.

## 4. Pilot at N=10, then scale

1. Run `python -m src.evaluation` over the 10 with both pipelines. Confirm sane
   IR + Ragas numbers.
2. If a question scores 0/0 on both, suspect the question (ambiguous, wrong gold).
   Read its retrieved articles — do they answer better than the gold? If yes, fix
   gold; if no, the corpus lacks it — drop the question.
3. Only after the pilot succeeds, push to 50.

## 5. Hold out the test split *before* tuning (see ADR 0002)

Before touching `TOP_K_VECTOR` / `GRAPH_HOP_DEPTH`:

1. Shuffle the 50 with a fixed seed.
2. First 35 → `eval.dev.jsonl` (tune here); last 15 → `eval.test.jsonl` (frozen).
3. Stratify: keep the 60/40 multi/single ratio in both — split multi and single
   separately, then concatenate.

`dataset.py` hardcodes one path; accept a path arg or point it at the file wanted.

## 6. Coverage tracking (lightweight)

Track in a side table to spot imbalance before all 50 are written:

| col | values |
|---|---|
| `regulation_type` | PMK / PP / UU / Perpu / Perpres |
| `topic` | DBH Sawit / PPh OP / PPN / Bea Materai / … |
| `hop_type` | single / multi |
| `degree_of_hub` | for bottom-up, in-degree of the seed article |

## 7. Time budget

- Bottom-up multi-hop: ~20 min (read hub + 3 neighbors, write answer).
- Top-down single-hop: ~10 min (grep + verify + write).
- 30 multi × 20 + 20 single × 10 = 800 min ≈ **13 hours**. Spread over 4–5
  sessions — quality degrades fast in one sitting.
