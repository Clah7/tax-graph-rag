# RAGAS generation-side eval — runbook

Closes the last untested axis (TODO §2): graph context may improve *answers*
even where ID-recall ties. Scores the cached answers in the v50 test runs
(`hyb_test_v50.jsonl`, baseline + graph) with LLM-judge metrics, then reports the
paired Wilcoxon + bootstrap CI — same statistical footing as the IR metrics.

Two stages, deliberately dep-isolated:
- **Stage A** (`scripts/ragas_score.py`) runs under an isolated venv with RAGAS
  0.2.x. It only reads the cached run JSONL — fully decoupled from the retrieval
  pipeline (which never imports langchain).
- **Stage B** (`scripts/ragas_stats.py`) runs under the `skripsi` env (scipy +
  `src`), reusing `src.evaluation.stats.paired_test`.

## Why an API judge

Local 9b judges are inadequate for RAGAS's structured-output metrics (verified
one row each, 2026-07-06/07):
- `gemma2:9b` (independent): faithfulness + context_recall → **NaN** (can't emit
  RAGAS's JSON), ~6.5 min/row → only 3/5 metrics after ~7h.
- `qwen3.5:9b` (self-judge): thinking model, >5.5 min for the first metric alone,
  impractically slow, plus self-judge bias.

`claude-haiku-4-5` as judge fixes speed + parsing + independence for ~$3–4 total
(66 rows × ~12 calls). Embeddings stay local (`qwen3-embedding:0.6b`) — only the
judge LLM hits the API, keeping cost/calls down. Disclose in BAB IV: independent
frontier judge (≠ the qwen3.5:9b generator), so faithfulness/correctness are not
self-judged.

## One-time venv setup (already done on this machine)

```bash
python3 -m venv ~/.venvs/ragas-eval
~/.venvs/ragas-eval/bin/pip install "ragas==0.2.14" langchain-ollama \
    langchain-anthropic datasets
```

RAGAS 0.2.14 hard-imports `langchain_community.chat_models.vertexai.ChatVertexAI`
at module load, which newer langchain-community removed. A shim satisfies the
import (Vertex is never used — judge is Ollama or Anthropic):

```bash
# .../site-packages/langchain_community/chat_models/vertexai.py
# class ChatVertexAI(BaseChatModel): raise NotImplementedError on init
```

If the venv is ever rebuilt, re-add that shim file (see git history of this doc /
the scratchpad `smoke.py`), or ragas import will fail on `ModuleNotFoundError`.

## Run (when ANTHROPIC_API_KEY is available)

```bash
export ANTHROPIC_API_KEY=sk-ant-...          # from console.anthropic.com

# Stage A — score both systems (resumable; each row written immediately)
for sys in baseline graph; do
  ~/.venvs/ragas-eval/bin/python scripts/ragas_score.py \
    --provider anthropic --judge claude-haiku-4-5 --max-workers 4 \
    --in  data/eval_runs/$sys/hyb_test_v50.jsonl \
    --out data/eval_runs/_reports/ragas/${sys}_hyb_test_v50.jsonl
done

# Stage B — paired stats (run under skripsi env)
python scripts/ragas_stats.py \
  --baseline data/eval_runs/_reports/ragas/baseline_hyb_test_v50.jsonl \
  --graph    data/eval_runs/_reports/ragas/graph_hyb_test_v50.jsonl \
  --out      data/eval_runs/_reports/ragas/hyb_test_v50_stats.csv
# optional slices: --hop multi  /  --hop single
```

Metrics: faithfulness, answer_relevancy, answer_correctness, context_precision,
context_recall. Stage A is resumable — re-running skips ids already in the out
file, so an interrupted batch just continues.

## Local fallback (free, no card, 3/5 metrics)

```bash
~/.venvs/ragas-eval/bin/python scripts/ragas_score.py \
  --provider ollama --judge gemma2:9b \
  --in data/eval_runs/baseline/hyb_test_v50.jsonl \
  --out data/eval_runs/_reports/ragas/baseline_gemma_hyb_test_v50.jsonl
```

faithfulness + context_recall come back NaN (Stage B drops NaN pairs), so report
only answer_relevancy / answer_correctness / context_precision from this path.
