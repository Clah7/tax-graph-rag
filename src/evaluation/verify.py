"""verify.py — interactive CLI to manually check eval.jsonl ground truth.

Walks through each row, prints the question, the drafted gold_answer, and the
full content of every gold pasal pulled from data/processed/articles.json so
you can read them side-by-side and mark the row verified.

Usage
-----
    # walk every row from the top
    python -m src.evaluation verify

    # skip rows whose notes don't start with "DRAFT" (i.e. already verified)
    python -m src.evaluation verify --only-drafts

    # jump straight to a specific question id
    python -m src.evaluation verify --id q005

Per-row commands (shown in the prompt)
--------------------------------------
    enter / n   next row, no change
    v           overwrite notes with "VERIFIED <today>" and advance
    p           previous row
    e           edit the notes field inline (prompts for new text)
    w           write changes to eval.jsonl now (atomic)
    q           quit (prompts to save if there are unsaved changes)

Behaviour notes
---------------
- Saves are atomic: writes to eval.jsonl.tmp then os.replace, so Ctrl-C is safe.
- `v` overwrites notes; use `e` if you want to keep context (e.g.
  "VERIFIED 2026-06-16 - added huruf b-h to gold_answer").
- Bigger edits (rewriting gold_answer, fixing gold_article_ids) are easier in
  the IDE - this CLI is for the read-and-confirm pass.
- A gold_article_id printed as "!! NOT FOUND" means the parser dropped that
  pasal from articles.json; cross-check against data/raw_pdfs/.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from src.config import ARTICLES_JSON, BASE_DIR

EVAL_PATH = Path(BASE_DIR) / "data" / "ground_truth" / "eval.jsonl"

SEP = "=" * 72
SUB = "-" * 72


def _load_articles() -> dict:
    with open(ARTICLES_JSON, encoding="utf-8") as f:
        arts = json.load(f)
    return {(a["regulation_id"], a["article_number"]): a for a in arts}


def _load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _save_rows(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _is_verified(row: dict) -> bool:
    return not row.get("notes", "").lstrip().upper().startswith("DRAFT")


def _show_article(articles: dict, gid: str) -> None:
    if "::" not in gid:
        print(f"  !! malformed id: {gid}")
        return
    reg, art = gid.split("::", 1)
    a = articles.get((reg, art))
    if a is None:
        print(f"  !! NOT FOUND in articles.json: {gid}")
        return
    refs = a.get("references") or []
    xrefs = a.get("cross_regulation_references") or []
    print(f"{SUB}\n{gid}   (refs={refs}  xrefs={xrefs})\n{SUB}")
    print(a.get("content", "").strip())


def _render(row: dict, idx: int, total: int, articles: dict) -> None:
    status = "VERIFIED" if _is_verified(row) else "DRAFT"
    print("\n" + SEP)
    print(f"[{idx + 1}/{total}] {row['id']}   hop={row.get('hop_type', 'single')}   [{status}]")
    print(SEP)
    print("\nQUESTION:")
    print(f"  {row['question']}")
    print("\nGOLD ANSWER:")
    print(f"  {row.get('gold_answer', '')}")
    print(f"\nGOLD ARTICLES ({len(row.get('gold_article_ids', []))}):")
    for gid in row.get("gold_article_ids", []):
        print()
        _show_article(articles, gid)
    print("\nNOTES:")
    print(f"  {row.get('notes', '')}")
    print()


def _flush_save(path: Path, rows: list[dict], dirty: bool) -> bool:
    if not dirty:
        return False
    _save_rows(path, rows)
    print(f"  saved → {path}")
    return True


def verify(only_drafts: bool = False, jump_id: str | None = None,
           eval_path: Path = EVAL_PATH) -> None:
    print(f"loading articles from {ARTICLES_JSON} ...")
    articles = _load_articles()
    rows = _load_rows(eval_path)
    print(f"loaded {len(rows)} rows from {eval_path}\n")

    i = 0
    if jump_id:
        for k, r in enumerate(rows):
            if r["id"] == jump_id:
                i = k
                break
        else:
            print(f"id {jump_id!r} not found — starting at row 0")

    dirty = False
    while 0 <= i < len(rows):
        row = rows[i]
        if only_drafts and _is_verified(row):
            i += 1
            continue

        _render(row, i, len(rows), articles)
        cmd = input(
            "[enter]=next  [v]erify  [p]rev  [e]dit-notes  [w]rite  [q]uit  > "
        ).strip().lower()

        if cmd in ("q", "quit"):
            break
        if cmd in ("", "n", "next", "s", "skip"):
            i += 1
        elif cmd in ("p", "prev"):
            i = max(0, i - 1)
        elif cmd in ("v", "verify"):
            row["notes"] = f"VERIFIED {date.today().isoformat()}"
            dirty = True
            i += 1
        elif cmd in ("e", "edit"):
            print("current notes:")
            print(f"  {row.get('notes', '')}")
            new = input("new notes (blank=keep): ")
            if new:
                row["notes"] = new
                dirty = True
        elif cmd in ("w", "write", "save"):
            if _flush_save(eval_path, rows, dirty):
                dirty = False
            else:
                print("  nothing to save")
        else:
            input(f"unknown: {cmd!r}. press enter to continue")

    if dirty:
        ans = input("\nunsaved changes — save? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            _flush_save(eval_path, rows, True)
        else:
            print("  discarded")
    else:
        print("\nno changes")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.evaluation verify")
    p.add_argument("--id", help="jump to a specific question id (e.g. q005)")
    p.add_argument("--only-drafts", action="store_true",
                   help="skip rows whose notes don't start with DRAFT")
    args = p.parse_args(argv)
    verify(only_drafts=args.only_drafts, jump_id=args.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
