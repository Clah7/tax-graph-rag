"""
CLI for the evaluation harness.

Workflow:
    # 1. Generate answers for each system (resumable; appends to JSONL cache).
    python -m src.evaluation run --system baseline --run-id v1
    python -m src.evaluation run --system graph    --run-id v1

    # 2. Build reports. --with-ragas adds LLM-judge metrics on top of IR metrics.
    python -m src.evaluation report --run-id v1
    python -m src.evaluation report --run-id v1 --with-ragas --tag v1_ragas
"""
import argparse
import logging
import sys

import json
from pathlib import Path

from src.config import BASE_DIR
from src.evaluation.dataset import load_dataset
from src.evaluation.report import report_from_runs
from src.evaluation.runner import run_system
from src.evaluation.verify import verify as verify_ground_truth


def _split_items(split: str):
    """Return eval items, optionally filtered to the dev/test split."""
    items = load_dataset()
    if split == "all":
        return items
    split_path = Path(BASE_DIR) / "data" / "ground_truth" / "split.json"
    if not split_path.exists():
        raise SystemExit(f"--split {split} needs {split_path}; run `python -m scripts.make_split`.")
    ids = set(json.loads(split_path.read_text(encoding="utf-8"))[split])
    return [it for it in items if it.id in ids]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(prog="python -m src.evaluation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run a pipeline over the eval set.")
    p_run.add_argument("--system", required=True, choices=["baseline", "graph"])
    p_run.add_argument("--run-id", default="default")
    p_run.add_argument("--no-resume", action="store_true",
                       help="Re-run questions already present in the cache.")
    p_run.add_argument("--hybrid", action="store_true",
                       help="Seed with hybrid lexical+dense retrieval.")
    p_run.add_argument("--alpha", type=float, default=None,
                       help="Override GRAPH_RERANK_ALPHA (graph only).")
    p_run.add_argument("--split", choices=["dev", "test", "all"], default="all",
                       help="Restrict to a ground-truth split (data/ground_truth/split.json).")

    p_rep = sub.add_parser("report", help="Build per-question + summary CSVs.")
    p_rep.add_argument("--run-id", default="default")
    p_rep.add_argument("--tag", default=None)
    p_rep.add_argument("--with-ragas", action="store_true",
                       help="Add Ragas LLM-judge metrics (requires `ragas`).")
    p_rep.add_argument("--k", type=int, nargs="*", default=[1, 3, 5, 10, 20],
                       help="K values for recall/precision/hit@k.")

    p_ver = sub.add_parser("verify", help="Interactively check eval.jsonl gold labels.")
    p_ver.add_argument("--id", help="Jump to a specific question id (e.g. q005).")
    p_ver.add_argument("--only-drafts", action="store_true",
                       help="Skip rows whose notes don't start with DRAFT.")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        import src.config as config
        if args.hybrid:
            config.USE_HYBRID_SEEDING = True
        items = _split_items(args.split)
        run_meta = {
            "seeding": "hybrid" if args.hybrid else "dense",
            "alpha": args.alpha if args.alpha is not None else config.GRAPH_RERANK_ALPHA,
            "split": args.split,
        }
        logging.info("run config: %s", run_meta)
        run_system(args.system, run_id=args.run_id, resume=not args.no_resume,
                   items=items, alpha=args.alpha, run_meta=run_meta)
        return 0

    if args.cmd == "verify":
        verify_ground_truth(only_drafts=args.only_drafts, jump_id=args.id)
        return 0

    if args.cmd == "report":
        paths = report_from_runs(
            run_id=args.run_id,
            tag=args.tag,
            with_ragas=args.with_ragas,
            k_values=tuple(args.k),
        )
        for name, path in paths.items():
            print(f"{name}: {path}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
