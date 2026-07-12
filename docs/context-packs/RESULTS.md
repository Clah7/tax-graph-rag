# Context Pack — RESULTS

Authoritative results for the thesis results chapter. Numbers copied verbatim
from `data/eval_runs/` and `STATUS.md`.

The eval set is now at **target size (50), all VERIFIED**, split frozen (ADR 0007).
The v50 IR headline in §0 is the current defensible result. Generation-side quality
(RAGAS) is now **run** — see §0.1. Still open (so keep the "provisional" tag in
prose): test n=33 is modest. Do NOT round differently or invent numbers.

Last synced from repo: 2026-07-12 (v50 IR headline §0 + RAGAS §0.1; §1–§7 are the
superseded **n=16** snapshot, kept for provenance).

---

## 0. v50 headline (test n=33, 2026-07-05, verified & frozen set)

Fresh stratified split (ADR 0007): dev 17 / test 33; 8 cross-reg multi in test.
Alpha frozen (0.10 hybrid, 0.15 dense ablation) — NOT re-tuned. Paired bootstrap
95% CIs (10k resamples). Runs: `hyb_test_v50`, `dense_test_v50`.

Hybrid baseline → hybrid+graph (`hyb_test_v50`):

| slice | metric | baseline | graph | Δ | 95% CI | Wilcoxon p | W/L |
|---|---|---|---|---|---|---|---|
| all | recall@5 | 0.571 | **0.677** | **+0.106** | [+0.020, +0.202] | **0.044** | 7/1 |
| all | precision@5 | 0.170 | 0.212 | +0.042 | [+0.006, +0.079] | **0.035** | 7/1 |
| all | hit@5 | 0.758 | 0.848 | +0.091 | [−0.030, +0.212] | 0.180 | 4/1 |
| multi | recall@5 | 0.412 | 0.544 | +0.132 | [+0.009, +0.263] | 0.079 | 6/1 |
| single | recall@5 | 0.786 | 0.857 | +0.071 | [0.000, +0.214] | 0.317 | 1/0 |

Dense ablation (`dense_test_v50`): graph **null** — recall@5 0.470→0.490 (Δ=+0.020,
CI [−0.081, +0.116], p=0.55). The "null on dense seeds, decisive on hybrid seeds"
2×2 story **holds** at n=50.

Honest reading:
- Core claim survives the larger, harder set: recall@5 **+0.106, significant
  (p=0.044), CI excludes 0**, corroborated by a significant precision@5 gain.
- Effect **moderated** vs the old n=16 (Δ 0.177→0.106; p 0.026→0.044) — larger n
  pulled the point estimate down but confirmed direction with a proper CI.
- **Soft spot:** the multi-hop slice effect is large (Δ=+0.132, CI excludes 0, 6/1)
  but Wilcoxon is only marginal (p=0.079) at n=19 — state plainly in BAB IV.
- **Specificity mostly holds:** single-hop controls barely move (+0.071, ns).

---

## 0.1 Generation-side quality — RAGAS (test n=33, 2026-07-12)

LLM-judge metrics over the **cached answers** in the v50 test runs
(`hyb_test_v50.jsonl`, baseline + graph). Judge = `claude-haiku-4-5` (independent
of the `qwen3.5:9b` generator → faithfulness/correctness are NOT self-judged);
embeddings local (`qwen3-embedding:0.6b`). Same paired footing as IR: Wilcoxon +
bootstrap 95% CI. Scorer `scripts/ragas_score.py`, stats `scripts/ragas_stats.py`,
runbook `docs/ragas-eval-runbook.md`. Artifacts under
`data/eval_runs/_reports/ragas/`.

| slice | metric | baseline | graph | Δ | 95% CI | Wilcoxon p | W/L |
|---|---|---|---|---|---|---|---|
| all | faithfulness | 0.530 | 0.570 | +0.041 | [−0.057, +0.133] | 0.360 | 17/15 |
| all | answer_relevancy | 0.461 | 0.538 | +0.078 | [−0.002, +0.166] | 0.179 | 16/12 |
| all | answer_correctness | 0.523 | 0.553 | +0.029 | [−0.034, +0.091] | 0.339 | 19/14 |
| all | context_precision | 0.543 | 0.552 | +0.010 | [−0.099, +0.127] | 0.954 | 9/15 |
| all | context_recall | 0.752 | 0.814 | +0.062 | [−0.038, +0.170] | 0.328 | 6/5 |
| multi | faithfulness | 0.569 | 0.637 | +0.068 | [−0.041, +0.177] | 0.215 | 11/7 |
| multi | answer_relevancy | 0.488 | 0.584 | +0.096 | [−0.029, +0.232] | 0.286 | 11/7 |
| multi | answer_correctness | 0.521 | 0.536 | +0.015 | [−0.057, +0.089] | 0.768 | 10/9 |
| multi | context_precision | 0.496 | 0.459 | **−0.037** | [−0.201, +0.127] | 0.615 | 5/9 |
| multi | context_recall | 0.645 | 0.730 | +0.085 | [−0.086, +0.272] | 0.444 | 5/5 |
| single | context_precision | 0.607 | 0.680 | +0.073 | [−0.056, +0.225] | 0.646 | 4/6 |
| single | context_recall | 0.897 | 0.929 | +0.032 | [+0.000, +0.095] | 0.317 | 1/0 |

Honest reading:
- Graph is **directionally ahead on all 5 overall metrics, but NONE is
  significant** — every CI crosses 0, all p > 0.05. n=33/19/14 is under-powered for
  the noisier LLM-judge scale; report as a *consistent trend*, not a win.
- The lean concentrates on **multi-hop answer quality** (faithfulness +0.068,
  answer_relevancy +0.096, context_recall +0.085) — same axis the IR recall gain
  lives on: graph pulls in the paired cross-reg article, so answers are more
  grounded and complete.
- **One honest wrinkle:** multi-hop **context_precision dips −0.037** — graph
  expansion admits some off-target articles even as it lifts recall (the classic
  recall↑/precision↓ of expansion). ns, but state it.
- **Controls ~flat** (single-hop): supports specificity, though context_precision
  +0.073 leans graph slightly more than an ideal null.
- Net: the generation-side story **corroborates the IR headline directionally and
  does not contradict it** — graph does not hurt answer quality, and trends the
  right way where it should (multi-hop). Not an independent significant win.

---

## 1. Seeding diagnosis (the real bottleneck)  *(n=16 snapshot)*

Gold is MIS-RANKED, not missing:
- **41/44 gold IDs are within the dense top-200**, just buried below the top-5
  cutoff (e.g. Pasal 156 @174, Pasal 2 @56, Pasal 87 @64, Pasal 3 @48).
- Only **3/44** gold IDs are truly absent from the pool.

Interpretation: the 0.6b embedding model recalls the right articles but ranks
them poorly. This motivates hybrid (lexical+dense) seeding.

---

## 2. Hybrid vs dense seeding (retrieval-only, held-out test)

| metric | dense-only | hybrid (RRF) | test delta |
|---|---|---|---|
| recall@5 | 0.469 | 0.521 | +0.052 |
| hit@5 | 0.625 | 0.750 | +0.125 |
| MRR | 0.424 | 0.547 | +0.123 |

Lexical signal anchors cited terms ("Pajak Hotel", regulation names) the dense
model smears. RRF k=60 (standard, untuned).

---

## 3. The 2×2 headline result (held-out test, n=16)

| system | recall@5 | hit@5 | MRR |
|---|---|---|---|
| dense-baseline | 0.469 | 0.625 | 0.424 |
| hybrid-baseline | 0.521 | 0.750 | 0.547 |
| dense + graph (α=0.15) | 0.469 | 0.563 | 0.440 |
| **hybrid + graph (α=0.10)** | **0.698** | **0.938** | 0.477 |

**Thesis headline comparison** (baseline = hybrid; GraphRAG = hybrid + graph):
- recall@5 **0.521 → 0.698**, Wilcoxon **p=0.026**, 6 wins / 0 losses.
- hit@5 0.750 → 0.938 (p=0.083). Gold reaches the LLM for **15/16** test questions.
- MRR dip −0.07 (not significant): first gold slips to rank 2–3, immaterial for
  context-filling.

---

## 4. Key finding: graph value depends on seed quality

- Graph expansion is **NULL on dense seeds** (recall@5 p=1.0) but **DECISIVE on
  hybrid seeds** (recall@5 0.521→0.698, p=0.026).
- Interpretation: the graph win only materializes once seeds land in the RIGHT
  regulation, so expansion can follow the cross-regulation REFERENCES edge to the
  paired article. This is the conceptual reason the baseline must be hybrid.

End-to-end (dense-baseline → hybrid+graph): recall@5 **+0.23 (+49% relative)**,
hit@5 **+0.31**.

---

## 5. Negative / null results (report honestly — these are assets)

- **Null result on IR re-ranking:** dev tuning picked α=0.15 (recall@5
  .375→.500) but it is a **WASH on held-out test** (recall@5 .469→.469, hit@5
  .625→.563, MRR .424→.440). The dev gain was n=8 noise. Ranking is NOT the
  bottleneck; seeding is.
- **Naive-version regression:** an earlier α=0.5 without hub damping made
  amendment-law hubs (UU 1/2022, UU 18/~1997) displace gold seeds — test MRR
  0.41→0.19. This motivated the degree-damped + symmetric boost.
- **Early append-only retriever (run v24):** baseline and graph identical at
  top-5 by construction; graph only diverged at deep k (recall@20 +0.13, p=0.03)
  bought with precision collapse and 147-article / 193s contexts hitting Ollama's
  300s timeout. Superseded by strict-parity truncation.

---

## 6. Statistical harness

`eval run --hybrid/--alpha/--split` runs `dense_test` + `hyb_test` on the test
split (n=16), paired stats (Wilcoxon / paired-t):
- Hybrid seeds: graph lifts recall@5 0.521→0.698 (Wilcoxon p=0.026, 6 wins/0
  losses), hit@5 0.750→0.938 (p=0.083).
- Dense seeds: graph null (recall@5 p=1.0).
- MRR dip −0.07 (ns).

Run artifacts: `data/eval_runs/baseline/`, `data/eval_runs/graph/`,
per-question + summary CSVs under `data/eval_runs/_reports/`.

---

## 7. Limitations of the current results

- **Statistical power:** test n=16 is underpowered; results provisional until the
  eval set reaches target (50). *(Superseded by the v50 split; §0/§0.1 are current.)*
- **RAGAS run (§0.1):** generation-side quality now measured with an independent
  `claude-haiku-4-5` judge — graph directionally ahead, none significant at n=33.
- **Data issues:** OCR `O`→`0` (~0.2%), ~1,157 omnibus ID collisions remain.
