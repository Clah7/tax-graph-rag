"""
ragas_score.py — Stage A of the generation-side eval.

Reads a run's cached JSONL (id, question, answer, contexts, gold_answer) and
scores each row with RAGAS (LLM-judge), writing one result per line to an
output JSONL *as it goes* so the batch is resumable and crash-safe.

Deps are isolated: run this with the dedicated `~/.venvs/ragas-eval` interpreter
(ragas 0.2.x + langchain-ollama), NOT the `skripsi` env (langchain 1.x). The
`skripsi` retrieval pipeline never imports langchain, so the two never collide.

Judge — pick a model *other than* the qwen3.5:9b generator to avoid self-judge
bias (the caveat `ragas_metrics.py` warns about):
  * `--provider anthropic --judge claude-haiku-4-5` (recommended): reliable
    structured output + fast; reads ANTHROPIC_API_KEY. Local 9b models (gemma2,
    qwen3.5) NaN on faithfulness/context_recall — they can't emit RAGAS's JSON.
  * `--provider ollama --judge gemma2:9b`: local/free but only produces 3/5
    metrics (faithfulness + context_recall fail to parse) and is ~6.5 min/row.
Embeddings always stay on qwen3-embedding:0.6b (local/free) to match corpus space.

Stage B (`scripts/ragas_stats.py`, run under `skripsi`) reads the two output
JSONLs and emits the paired Wilcoxon + bootstrap-CI table via
`src.evaluation.stats`.

Usage (per system) — Anthropic judge (turnkey once ANTHROPIC_API_KEY is set):
    export ANTHROPIC_API_KEY=sk-ant-...
    ~/.venvs/ragas-eval/bin/python scripts/ragas_score.py \
        --provider anthropic --judge claude-haiku-4-5 --max-workers 4 \
        --in  data/eval_runs/baseline/hyb_test_v50.jsonl \
        --out data/eval_runs/_reports/ragas/baseline_hyb_test_v50.jsonl
    # repeat with graph/hyb_test_v50.jsonl -> graph_hyb_test_v50.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import time
import warnings

warnings.filterwarnings("ignore")

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
]


def _load_rows(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _done_ids(out_path: str) -> set[str]:
    if not os.path.exists(out_path):
        return set()
    ids = set()
    with open(out_path) as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def _build_metrics(names: list[str]):
    from ragas.metrics import (
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    table = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "answer_correctness": answer_correctness,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    return [table[n] for n in names]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama",
                    help="judge LLM backend. anthropic reads ANTHROPIC_API_KEY.")
    ap.add_argument("--judge", default="gemma2:9b",
                    help="judge model id (e.g. gemma2:9b, or claude-haiku-4-5 with --provider anthropic)")
    ap.add_argument("--embed", default="qwen3-embedding:0.6b",
                    help="embedding model (always Ollama, kept local/free)")
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--metrics", nargs="+", default=METRIC_NAMES)
    ap.add_argument("--limit", type=int, default=0, help="score at most N new rows (0 = all)")
    ap.add_argument("--timeout", type=int, default=900,
                    help="per-metric job timeout (s); local 9b judges are slow")
    ap.add_argument("--max-workers", type=int, default=1,
                    help="concurrent metric jobs. 1 for local Ollama (serializes anyway); "
                         "raise (e.g. 4) for the Anthropic API to run metrics in parallel.")
    args = ap.parse_args()

    from datasets import Dataset
    from langchain_ollama import OllamaEmbeddings
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    # Ollama serializes requests to one loaded model, so concurrent metric jobs
    # just queue and blow the default 180s per-job timeout (NaNs) — keep
    # max_workers=1 there. The Anthropic API handles concurrency, so a higher
    # value parallelises the ~12 calls/row.
    run_config = RunConfig(max_workers=args.max_workers, timeout=args.timeout)

    metrics = _build_metrics(args.metrics)
    if args.provider == "anthropic":
        # Independent judge (not the qwen3.5:9b generator): reliable structured
        # output + fast, unlike local 9b models. temperature=0 for reproducibility.
        from langchain_anthropic import ChatAnthropic
        judge = LangchainLLMWrapper(
            ChatAnthropic(model=args.judge, temperature=0, timeout=args.timeout, max_retries=3)
        )
    else:
        from langchain_ollama import ChatOllama
        judge = LangchainLLMWrapper(
            ChatOllama(model=args.judge, base_url=args.base_url, temperature=0)
        )
    emb = LangchainEmbeddingsWrapper(
        OllamaEmbeddings(model=args.embed, base_url=args.base_url)
    )

    rows = _load_rows(args.in_path)
    done = _done_ids(args.out_path)
    pending = [r for r in rows if r["id"] not in done]
    if args.limit:
        pending = pending[: args.limit]

    os.makedirs(os.path.dirname(args.out_path), exist_ok=True)
    print(f"[ragas] {args.in_path}: {len(rows)} rows, {len(done)} done, "
          f"{len(pending)} to score, judge={args.judge}", flush=True)

    with open(args.out_path, "a") as out:
        for i, r in enumerate(pending, 1):
            t0 = time.time()
            ds = Dataset.from_list([{
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
                "ground_truth": r["gold_answer"],
            }])
            scored = evaluate(ds, metrics=metrics, llm=judge, embeddings=emb,
                              run_config=run_config)
            rec = scored.to_pandas().to_dict(orient="records")[0]
            row_out = {"id": r["id"], "hop_type": r.get("hop_type")}
            for name in args.metrics:
                val = rec.get(name)
                row_out[name] = float(val) if val is not None else float("nan")
            out.write(json.dumps(row_out) + "\n")
            out.flush()
            dt = time.time() - t0
            print(f"[ragas] {i}/{len(pending)} {r['id']} {dt:.0f}s "
                  + " ".join(f"{k}={row_out[k]:.3f}" for k in args.metrics), flush=True)

    print(f"[ragas] done: {args.out_path}", flush=True)


if __name__ == "__main__":
    main()
