"""
normalise_dry_run.py — Compare current vs. proposed _normalise() match rates.

No data is written. Reports:
  - before/after counts of files that match a metadata entry
  - before/after counts of unmatched metadata entries
  - collisions where >1 file maps to the same normalised key
  - 20 random newly-recovered (file, metadata_number) pairs for spot-check
  - 20 random STILL-orphan filenames so we can see what the next rule needs
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def normalise_current(text: str) -> str:
    return re.sub(r'[\s_]+', ' ', text).strip().upper()


# Proposed: strip /, ., - (and treat as whitespace); drop trailing dup suffix
# like "_1"; then collapse runs.
_TRAILING_DUP_RE = re.compile(r'(?:\s|_)\d{1,2}$')
_PUNCT_RE = re.compile(r'[\s_/\.\-]+')


def normalise_proposed(text: str) -> str:
    s = text.strip()
    # Convert separators to single spaces
    s = _PUNCT_RE.sub(' ', s)
    s = s.strip().upper()
    # Drop a trailing single/double-digit token that looks like a duplicate-copy suffix
    # ("01 PMK 010 2011 1" -> "01 PMK 010 2011"). Only strip when there are already
    # >=4 tokens so we don't accidentally clip a legitimate trailing year.
    tokens = s.split(' ')
    if len(tokens) >= 5 and tokens[-1].isdigit() and len(tokens[-1]) <= 2:
        s = ' '.join(tokens[:-1])
    return s


def main() -> None:
    with open(ROOT / "jdih_metadata.json", encoding="utf-8") as fh:
        meta_list: list[dict] = json.load(fh)

    pdf_dir = ROOT / "data" / "raw_pdfs"
    files = sorted(
        list(pdf_dir.glob("*.pdf")) +
        list(pdf_dir.glob("*.html")) +
        list(pdf_dir.glob("*.htm"))
    )

    # Build both metadata indexes
    meta_cur: dict[str, str] = {}
    meta_new: dict[str, str] = {}
    meta_new_collisions: dict[str, list[str]] = defaultdict(list)
    for r in meta_list:
        rn = r["regulation_number"]
        meta_cur[normalise_current(rn)] = rn
        nk = normalise_proposed(rn)
        if nk in meta_new and meta_new[nk] != rn:
            meta_new_collisions[nk].append(rn)
        meta_new[nk] = rn

    matched_cur = 0
    matched_new = 0
    newly_recovered: list[tuple[str, str]] = []  # (filename, metadata regulation_number)
    still_orphans: list[str] = []
    file_new_keys: dict[str, list[str]] = defaultdict(list)  # collision detection on file side

    for f in files:
        kc = normalise_current(f.stem)
        kn = normalise_proposed(f.stem)
        file_new_keys[kn].append(f.name)

        cur_hit = kc in meta_cur
        new_hit = kn in meta_new

        if cur_hit:
            matched_cur += 1
        if new_hit:
            matched_new += 1
        if new_hit and not cur_hit:
            newly_recovered.append((f.name, meta_new[kn]))
        if not new_hit:
            still_orphans.append(f.name)

    # File-side collisions under new normalisation (multiple files -> same key)
    file_collisions = {k: v for k, v in file_new_keys.items() if len(v) > 1}

    print("=" * 70)
    print("FILE → METADATA match counts")
    print("=" * 70)
    print(f"  total files:                       {len(files)}")
    print(f"  matched (CURRENT normalise):       {matched_cur}")
    print(f"  matched (PROPOSED normalise):      {matched_new}")
    print(f"  newly recovered files:             {matched_new - matched_cur}")
    print()

    matched_cur_meta_keys = sum(1 for r in meta_list if normalise_current(r["regulation_number"]) in {normalise_current(f.stem) for f in files})
    file_new_set = {normalise_proposed(f.stem) for f in files}
    matched_new_meta_keys = sum(1 for r in meta_list if normalise_proposed(r["regulation_number"]) in file_new_set)
    print("METADATA → FILE coverage")
    print(f"  total metadata entries:            {len(meta_list)}")
    print(f"  with a matching file (CURRENT):    {matched_cur_meta_keys}")
    print(f"  with a matching file (PROPOSED):   {matched_new_meta_keys}")
    print(f"  metadata entries now reachable:    {matched_new_meta_keys - matched_cur_meta_keys}")
    print()

    print("COLLISIONS (could cause wrong matches under PROPOSED normalisation)")
    print(f"  multiple metadata entries → same key:  {len(meta_new_collisions)}")
    print(f"  multiple files            → same key:  {len(file_collisions)}")
    if meta_new_collisions:
        print("  meta-side examples (first 5):")
        for k, vs in list(meta_new_collisions.items())[:5]:
            all_for_key = [r["regulation_number"] for r in meta_list if normalise_proposed(r["regulation_number"]) == k]
            print(f"    {k!r}  <-  {all_for_key}")
    if file_collisions:
        print("  file-side examples (first 5):")
        for k, vs in list(file_collisions.items())[:5]:
            print(f"    {k!r}  <-  {vs}")
    print()

    print("20 random newly-recovered (file → metadata) pairs:")
    random.seed(7)
    sample = random.sample(newly_recovered, min(20, len(newly_recovered)))
    for fn, mn in sample:
        print(f"  {fn:<42} -> {mn!r}")
    print()

    print("20 random STILL-orphan filenames (what the next normalisation rule must cover):")
    sample2 = random.sample(still_orphans, min(20, len(still_orphans)))
    for fn in sample2:
        print(f"  {fn}")


if __name__ == "__main__":
    main()
