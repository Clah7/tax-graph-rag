"""
prototype_dedup.py — Measure (do not apply) a better dedup rule for the
article-ID collisions in ADR 0006.

Current ingestion keeps the LAST raw record per (regulation_id, article_number)
(Chroma `seen[id]=a`; Neo4j `ON MATCH SET a.text`). That arbitrarily can keep a
Penjelasan stub ("Cukup jelas.") over the batang tubuh.

This script classifies every multi-record group to separate the two distinct
problems in ADR 0006:

  * SELECTABLE  — after dropping penjelasan/trivial records, exactly one distinct
                  batang-tubuh body remains. A "prefer longest non-penjelasan"
                  rule fixes these outright.
  * COLLISION   — >=2 distinct substantive batang-tubuh bodies remain (omnibus
                  laws reusing Pasal numbers). Selection cannot fix these; they
                  need ID disambiguation. This script only counts them.

Run (analysis only, writes nothing):
    python -m scripts.prototype_dedup
"""
from __future__ import annotations

import collections
import json
import re

from src.config import ARTICLES_JSON

# Penjelasan (elucidation) records describe a Pasal rather than state the norm.
# Heuristic: they open by naming the structural unit they explain ("Ayat (1)",
# "Huruf a", "Angka 2") or are the boilerplate "Cukup jelas." Batang tubuh
# instead opens with a bare ayat marker "(1)" or the provision text directly.
_PENJELASAN_RE = re.compile(r"^\s*(Ayat\s*\(|Huruf\s|Angka\s|Cukup\s+jelas)", re.IGNORECASE)
_TRIVIAL_LEN = 15


def _body(rec: dict) -> str:
    return (rec.get("content") or rec.get("raw_text") or "").strip()


def _is_penjelasan(text: str) -> bool:
    return bool(_PENJELASAN_RE.match(text))


def _is_trivial(text: str) -> bool:
    return len(text) < _TRIVIAL_LEN


def _distinct_bodies(texts: list[str]) -> list[str]:
    """Collapse near-duplicates by their first 200 chars; keep the longest of each."""
    by_prefix: dict[str, str] = {}
    for t in texts:
        key = t[:200]
        if key not in by_prefix or len(t) > len(by_prefix[key]):
            by_prefix[key] = t
    return list(by_prefix.values())


def main() -> None:
    with open(ARTICLES_JSON, encoding="utf-8") as fh:
        data = json.load(fh)

    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in data:
        groups[(r.get("regulation_id"), str(r.get("article_number")))].append(r)

    n_groups = len(groups)
    n_multi = 0
    selectable = 0          # simple rule fixes outright
    collision = 0           # needs ID disambiguation (omnibus)
    all_trivial = 0         # even the best record is empty/"Cukup jelas."
    changed_vs_last = 0     # proposed survivor differs from current "keep last"

    collision_examples: list[str] = []

    for (reg, pasal), recs in groups.items():
        if len(recs) > 1:
            n_multi += 1

        bodies = [_body(r) for r in recs]
        # candidate batang-tubuh = non-penjelasan, non-trivial
        bt = [b for b in bodies if b and not _is_penjelasan(b) and not _is_trivial(b)]
        distinct_bt = _distinct_bodies(bt)

        if not distinct_bt:
            # nothing usable survived
            if len(recs) > 1:
                all_trivial += 1
            continue

        if len(distinct_bt) >= 2:
            collision += 1
            if len(collision_examples) < 8:
                collision_examples.append(f"{reg}::{pasal}  ({len(distinct_bt)} distinct bodies)")
        elif len(recs) > 1:
            selectable += 1

        # would the proposed survivor (longest batang tubuh) differ from keep-last?
        if len(recs) > 1:
            proposed = max(distinct_bt, key=len)
            current_last = bodies[-1]
            if proposed[:200] != current_last[:200]:
                changed_vs_last += 1

    print(f"total (reg,pasal) groups            : {n_groups:,}")
    print(f"groups with >1 raw record           : {n_multi:,}  ({100*n_multi/n_groups:.1f}%)")
    print("-" * 60)
    print(f"SELECTABLE (simple rule fixes)      : {selectable:,}")
    print(f"COLLISION  (needs ID disambiguation): {collision:,}")
    print(f"all-trivial survivors (no batang tubuh): {all_trivial:,}")
    print("-" * 60)
    print(f"IDs whose text would CHANGE vs keep-last: {changed_vs_last:,}")
    print()
    print("sample COLLISION groups (omnibus-style):")
    for e in collision_examples:
        print(f"  {e}")


if __name__ == "__main__":
    main()
