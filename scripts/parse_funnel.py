"""
parse_funnel.py — Replay parser filters without ingesting; report drop counts.

Buckets, in the order the parser applies them:
    1. orphan       — file stem doesn't map to a jdih_metadata.json entry
    2. image_only   — PDF avg chars/page < IMAGE_TEXT_THRESHOLD
    3. no_pasal     — passed image check but ARTICLE_HEADER_RE matched nothing
    4. error        — open/read raised an exception
    5. parsed       — would have produced >=1 article
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_acquisition.parser import (  # noqa: E402
    ARTICLE_HEADER_RE,
    IMAGE_TEXT_THRESHOLD,
    PDF_DIR,
    METADATA_JSON,
    _load_metadata,
    _normalise,
)


def classify(path_str: str, has_metadata: bool) -> tuple[str, str]:
    """Return (bucket, file_path_str)."""
    if not has_metadata:
        return ("orphan", path_str)

    path = Path(path_str)
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            import fitz  # imported in worker
            doc = fitz.open(path_str)
            total_chars = 0
            page_count = doc.page_count
            for page in doc:
                total_chars += len(page.get_text())
            avg = total_chars / max(page_count, 1)
            if avg < IMAGE_TEXT_THRESHOLD:
                doc.close()
                return ("image_only", path_str)
            full_text = "\n".join(page.get_text() for page in doc)
            doc.close()
        elif suffix in (".html", ".htm"):
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    with open(path_str, encoding=encoding, errors="strict") as fh:
                        raw = fh.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                with open(path_str, encoding="utf-8", errors="replace") as fh:
                    raw = fh.read()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "head"]):
                tag.decompose()
            full_text = soup.get_text(separator="\n")
        else:
            return ("other_ext", path_str)
    except Exception as exc:
        return (f"error:{type(exc).__name__}", path_str)

    parts = ARTICLE_HEADER_RE.split(full_text)
    if len(parts) < 3:
        return ("no_pasal", path_str)
    return ("parsed", path_str)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    pdf_dir = root / PDF_DIR
    metadata_path = root / METADATA_JSON

    print(f"Loading metadata: {metadata_path}")
    metadata = _load_metadata(str(metadata_path))
    print(f"  {len(metadata)} metadata entries (by normalised regulation_number).")

    all_files = sorted(
        list(pdf_dir.glob("*.pdf")) +
        list(pdf_dir.glob("*.html")) +
        list(pdf_dir.glob("*.htm"))
    )
    print(f"Scanning {len(all_files)} files in {pdf_dir} …")

    jobs: list[tuple[str, bool]] = []
    for f in all_files:
        jobs.append((str(f), _normalise(f.stem) in metadata))

    counts: Counter[str] = Counter()
    parsed_paths: list[str] = []
    image_only_paths: list[str] = []
    no_pasal_paths: list[str] = []

    start = time.time()
    done = 0
    with ProcessPoolExecutor() as ex:
        futures = [ex.submit(classify, p, hm) for p, hm in jobs]
        for fut in as_completed(futures):
            bucket, path = fut.result()
            counts[bucket] += 1
            if bucket == "parsed":
                parsed_paths.append(path)
            elif bucket == "image_only":
                image_only_paths.append(path)
            elif bucket == "no_pasal":
                no_pasal_paths.append(path)
            done += 1
            if done % 500 == 0:
                rate = done / (time.time() - start)
                print(f"  {done}/{len(jobs)}  ({rate:.0f}/s)")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s.")
    print("\n========== Drop-bucket counts ==========")
    total = sum(counts.values())
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        pct = 100.0 * v / total
        print(f"  {k:<24} {v:>6}  ({pct:5.1f}%)")
    print(f"  {'TOTAL':<24} {total:>6}")

    print(f"\nSample image_only (first 5): {image_only_paths[:5]}")
    print(f"Sample no_pasal   (first 5): {no_pasal_paths[:5]}")


if __name__ == "__main__":
    main()
