"""
parser.py — Extract and split Indonesian tax regulation PDFs into Pasal (Article) units.

Pipeline:
  data/raw_pdfs/*.pdf
      └─ fitz (PyMuPDF) text extraction
          └─ regex split on article headers  (Pasal N on its own line)
              └─ regex cross-reference detection
                  └─ data/processed/articles.json
"""
import json
import logging
import os
import re
from pathlib import Path

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PDF_DIR: str = "data/raw_pdfs"
METADATA_JSON: str = "jdih_metadata.json"
OUTPUT_JSON: str = "data/processed/articles.json"
TEST_LIMIT: int = 1  # Number of PDFs to process; set to None for all

# Minimum average characters per page before treating a PDF as image-only
IMAGE_TEXT_THRESHOLD: int = 50

# ---------------------------------------------------------------------------
# Regex Patterns
#
# ARTICLE_HEADER_RE: Matches "Pasal N" only when it appears on its own line
# (possibly with leading/trailing whitespace). This prevents cross-references
# like "...sebagaimana dimaksud dalam Pasal 4..." from being treated as
# article boundaries.
#
# CROSS_REF_RE: Captures every "Pasal N [ayat (M)]" mention within an
# article's text. These become the directed edges in the GraphRAG schema.
# ---------------------------------------------------------------------------
ARTICLE_HEADER_RE: re.Pattern[str] = re.compile(
    r'\n[ \t]*Pasal[ \t]+(\d+[A-Z]?)[ \t]*\n',
    re.IGNORECASE,
)

CROSS_REF_RE: re.Pattern[str] = re.compile(
    r'(?i)\bPasal\s+(\d+[A-Z]?)(?:\s+ayat\s+\((\d+)\))?',
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_metadata(path: str) -> dict[str, dict]:
    """
    Load jdih_metadata.json and return a dict keyed by normalised
    regulation_number so PDFs can be matched by filename stem.
    """
    with open(path, encoding="utf-8") as fh:
        records: list[dict] = json.load(fh)
    return {_normalise(r["regulation_number"]): r for r in records}


def _normalise(text: str) -> str:
    """Collapse whitespace/underscores for loose filename ↔ metadata matching."""
    return re.sub(r'[\s_]+', ' ', text).strip().upper()


def _extract_full_text(doc: fitz.Document) -> str:
    """Concatenate text from all pages with page-break newlines."""
    return "\n".join(page.get_text() for page in doc)


def _is_image_pdf(doc: fitz.Document) -> bool:
    """Return True if the average characters per page is below threshold."""
    total_chars = sum(len(page.get_text()) for page in doc)
    avg = total_chars / max(doc.page_count, 1)
    return avg < IMAGE_TEXT_THRESHOLD


def _clean(text: str) -> str:
    """Normalise whitespace for the `content` field."""
    # Collapse runs of spaces/tabs; reduce 3+ newlines to 2
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_references(article_text: str, self_number: str) -> list[str]:
    """
    Return a deduplicated list of article numbers mentioned in *article_text*,
    excluding self-references (where the cited number equals *self_number*).
    These correspond to (Article)-[:REFERENCES]->(Article) edges in Neo4j.
    """
    found: list[str] = []
    seen: set[str] = set()
    for m in CROSS_REF_RE.finditer(article_text):
        num = m.group(1).upper()
        if num != self_number.upper() and num not in seen:
            found.append(num)
            seen.add(num)
    return found


# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------
def parse_pdf(pdf_path: Path, regulation_id: str) -> list[dict]:
    """
    Open *pdf_path*, extract text, split into Pasal units, and return a
    list of article dicts ready for JSON serialisation.

    Raises:
        ValueError: if the PDF appears to be image-only.
    """
    doc = fitz.open(str(pdf_path))

    if _is_image_pdf(doc):
        doc.close()
        raise ValueError(
            f"PDF appears to be image-only (avg chars/page < {IMAGE_TEXT_THRESHOLD}): "
            f"{pdf_path.name}"
        )

    full_text = _extract_full_text(doc)
    doc.close()

    # re.split with a capturing group returns:
    # [pre_text, num1, chunk1, num2, chunk2, ...]
    parts = ARTICLE_HEADER_RE.split(full_text)

    # parts[0] is the preamble (Menimbang, Mengingat, etc.) — skip it.
    articles: list[dict] = []
    # Walk in steps of 2 starting from index 1: (article_number, content)
    for i in range(1, len(parts) - 1, 2):
        article_number: str = parts[i].strip().upper()
        raw_text: str = parts[i + 1]

        refs = _extract_references(raw_text, article_number)

        articles.append(
            {
                "regulation_id": regulation_id,
                "article_number": article_number,
                "content": _clean(raw_text),
                "raw_text": raw_text,
                "references": refs,
            }
        )

    return articles


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_all(
    pdf_dir: str = PDF_DIR,
    metadata_path: str = METADATA_JSON,
    output_path: str = OUTPUT_JSON,
    limit: int | None = TEST_LIMIT,
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    metadata = _load_metadata(metadata_path)
    pdf_files = sorted(Path(pdf_dir).glob("*.pdf"))

    if not pdf_files:
        logger.error("No PDF files found in '%s'.", pdf_dir)
        return

    if limit is not None:
        pdf_files = pdf_files[:limit]
        logger.info("TEST_LIMIT=%d — processing %d PDF(s).", limit, len(pdf_files))

    all_articles: list[dict] = []

    for pdf_path in pdf_files:
        # Map filename stem (e.g. "PMK_10_TAHUN_2026") → regulation_number
        stem_normalised = _normalise(pdf_path.stem)
        meta = metadata.get(stem_normalised)

        if meta is None:
            logger.warning(
                "No metadata entry for '%s' (normalised: '%s') — skipping.",
                pdf_path.name, stem_normalised,
            )
            continue

        regulation_id: str = meta["regulation_number"]
        logger.info("Parsing '%s'  →  regulation_id='%s'", pdf_path.name, regulation_id)

        try:
            articles = parse_pdf(pdf_path, regulation_id)
        except ValueError as exc:
            logger.error("[IMAGE-ONLY] %s", exc)
            continue
        except Exception as exc:
            logger.error("Unexpected error parsing '%s': %s", pdf_path.name, exc)
            continue

        logger.info(
            "  Extracted %d articles, %d total cross-references.",
            len(articles),
            sum(len(a["references"]) for a in articles),
        )
        all_articles.extend(articles)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(all_articles, fh, indent=2, ensure_ascii=False)

    logger.info(
        "Done. %d total articles written to '%s'.", len(all_articles), output_path
    )


if __name__ == "__main__":
    parse_all()
