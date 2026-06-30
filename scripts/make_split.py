"""
make_split.py — Deterministic dev/test split of the ground-truth eval set.

Run:
    python -m scripts.make_split [--dev-frac 0.34] [--seed 20260701]

Why: GraphRAG re-ranking has a tunable knob (GRAPH_RERANK_ALPHA). Methodology
discipline (CLAUDE.md) requires holding out the test split BEFORE tuning, so the
reported numbers are not fitted to the data they are measured on. This writes a
frozen split to data/ground_truth/split.json:

    {"seed": ..., "dev_frac": ..., "dev": [ids...], "test": [ids...]}

The split is stratified by hop_type (single/multi) so both slices appear in dev
and test, and is fully reproducible from (seed, dev_frac). Re-running with the
same args is idempotent. Tune alpha on `dev` only; report on `test`.
"""
import argparse
import json
import random
from pathlib import Path

from src.config import BASE_DIR
from src.evaluation.dataset import load_dataset

SPLIT_PATH = Path(BASE_DIR) / "data" / "ground_truth" / "split.json"


def make_split(dev_frac: float, seed: int) -> dict:
    items = load_dataset()
    by_hop: dict[str, list[str]] = {}
    for it in items:
        by_hop.setdefault(it.hop_type, []).append(it.id)

    rng = random.Random(seed)
    dev: list[str] = []
    test: list[str] = []
    for hop, ids in sorted(by_hop.items()):
        ids = sorted(ids)
        rng.shuffle(ids)
        n_dev = round(len(ids) * dev_frac)
        dev.extend(ids[:n_dev])
        test.extend(ids[n_dev:])

    return {
        "seed": seed,
        "dev_frac": dev_frac,
        "dev": sorted(dev),
        "test": sorted(test),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-frac", type=float, default=0.34)
    ap.add_argument("--seed", type=int, default=20260701)
    args = ap.parse_args()

    split = make_split(args.dev_frac, args.seed)
    SPLIT_PATH.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")

    items = {it.id: it.hop_type for it in load_dataset()}
    def hops(ids):
        s = sum(1 for i in ids if items[i] == "single")
        m = sum(1 for i in ids if items[i] == "multi")
        return f"{len(ids)} ({s} single, {m} multi)"

    print(f"Wrote {SPLIT_PATH}")
    print(f"  seed={split['seed']} dev_frac={split['dev_frac']}")
    print(f"  dev : {hops(split['dev'])}: {split['dev']}")
    print(f"  test: {hops(split['test'])}: {split['test']}")


if __name__ == "__main__":
    main()
