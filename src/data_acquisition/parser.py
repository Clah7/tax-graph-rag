"""
parser.py — Extract and split Indonesian tax regulation PDFs and HTML files into Pasal units.

Pipeline:
  data/raw_pdfs/*.pdf  |  data/raw_pdfs/*.html / *.htm
      └─ fitz (PyMuPDF) for PDF  |  BeautifulSoup for HTML
          └─ regex split on article headers  (Pasal N on its own line)
              └─ regex cross-reference detection
                  └─ data/processed/articles.json
"""
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path

import fitz  # PyMuPDF
from bs4 import BeautifulSoup

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
REGULATIONS_OUTPUT_JSON: str = "data/processed/regulations.json"
TEST_LIMIT: int | None = None  # Set to an int to limit files processed

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

# Intra-regulation: bare "Pasal N" or "Pasal N ayat (M)"
CROSS_REF_RE: re.Pattern[str] = re.compile(
    r'(?i)\bPasal\s+(\d+[A-Z]?)(?:\s+ayat\s+\((\d+)\))?',
)

# Inter-regulation: "Pasal N <RegType> [Republik Indonesia] Nomor X[/...] Tahun YYYY"
CROSS_REG_REF_RE: re.Pattern[str] = re.compile(
    r'(?i)\bPasal\s+(\d+[A-Z]?)(?:\s+ayat\s+\((\d+)\))?\s+'
    r'(Peraturan\s+Pemerintah\s+Pengganti\s+Undang-Undang'
    r'|Peraturan\s+Pemerintah'
    r'|Peraturan\s+Menteri\s+Keuangan'
    r'|Undang-Undang'
    r'|Keputusan\s+Menteri\s+Keuangan'
    r'|PERPU|Perppu|PP|PMK|UU|KMK)'
    r'(?:\s+Republik\s+Indonesia)?'
    r'\s+Nomor\s+(\d+)(?:/[^\s,;.()\n]+)?\s+[Tt]ahun\s+(\d{4})'
)

# ---------------------------------------------------------------------------
# AMENDS detection (title-driven, from jdih_metadata.json)
#
# Indonesian regulations reliably encode amendment/repeal targets in the
# regulation TITLE, e.g.
#     "Perubahan atas Peraturan Menteri Keuangan Nomor 9 Tahun 2025 ..."
#     "Pencabutan Peraturan Menteri Keuangan Nomor 45/PMK.011/2018 ..."
# We match the prefix ("Perubahan [Kedua/Ketiga/...] atas" or "Pencabutan")
# then extract the canonical id of the target regulation. Coverage on the
# corpus title set is ~92 %; the rest are out-of-scope (PER-DJP) or OCR typos.
# ---------------------------------------------------------------------------
AMENDS_PREFIX_RE: re.Pattern[str] = re.compile(
    r'(?i)^\s*'
    r'(?P<action>'
    r'Perubahan(?:\s+(?:Kedua|Ketiga|Keempat|Kelima|Keenam|Ketujuh|Kedelapan|Kesembilan|Kesepuluh))?\s+atas'
    r'|Pencabutan(?:\s+atas)?'
    r')\s+'
)

# Regulation reference inside a title. Accepts BOTH number formats:
#   "Nomor 9 Tahun 2025"           (modern)
#   "Nomor 240/PMK.06/2016"        (legacy MoF — year inside slash code)
TITLE_REG_REF_RE: re.Pattern[str] = re.compile(
    r'(?i)\b'
    r'(Peraturan\s+Pemerintah\s+Pengganti\s+Undang-Undang'
    r'|Peraturan\s+Pemerintah'
    r'|Peraturan\s+Menteri\s+Keuangan'
    r'|Undang-Undang'
    r'|Keputusan\s+Menteri\s+Keuangan'
    r'|PERPU|Perppu|PP|PMK|UU|KMK)'
    r'\s+Nomor\s+(\d+)'
    r'(?:'
        r'\s*/[^\s,;()]*?/(\d{4})'       # legacy slash format
        r'|\s+[Tt]ahun\s+(\d{4})'         # modern format
    r')'
)

# ---------------------------------------------------------------------------
# DEFINES detection (Pasal 1 definitional lists)
#
# Pasal 1 of an Indonesian regulation typically opens with
#     "Dalam Peraturan ... ini, yang dimaksud dengan:
#         1. <Term> adalah <definition>.
#         2. <Term>, [yang] selanjutnya disebut <Alias>, adalah <def>.
#         3. <Term> yang selanjutnya disingkat <Alias>, adalah <def>.
#         ..."
# We capture the <Term> only — the Concept node holds just `name`.
# Whitespace is normalised before matching to tolerate PDF line-break artefacts.
# ---------------------------------------------------------------------------
DEFINITION_RE: re.Pattern[str] = re.compile(
    # Boundary class includes ':' so the first item after
    # "yang dimaksud dengan:" is captured along with subsequent bullets
    # that follow a previous sentence terminator (. ; \n).
    r'(?:^|[\n.;:])\s*'
    r'(?:[a-zA-Z]\.|\d+\.)\s+'
    r'(?P<term>[^.;,\n]{2,100}?)'
    r'(?:'
        # Variant A: ", [yang] selanjutnya (disebut|disingkat) <name>[,]"
        r',\s*(?:yang\s+)?selanjutnya\s+(?:disebut(?:\s+juga)?|disingkat)\s+[^.,;\n]{1,80}?\s*,?'
        r'|'
        # Variant B: " yang selanjutnya (disebut|disingkat) <name>[,]"
        r'\s+yang\s+selanjutnya\s+(?:disebut(?:\s+juga)?|disingkat)\s+[^.,;\n]{1,80}?\s*,?'
    r')?'
    r'\s+adalah\b',
    re.IGNORECASE,
)

# Maps verbose regulation type names to short codes
_REG_TYPE_NORMALISE: list[tuple[str, str]] = [
    ("pengganti",        "PERPU"),
    ("pemerintah",       "PP"),
    ("menteri keuangan", "PMK"),
    ("undang",           "UU"),
    ("keputusan",        "KMK"),
    ("perpu",            "PERPU"),
    ("pp",               "PP"),
    ("pmk",              "PMK"),
    ("uu",               "UU"),
    ("kmk",              "KMK"),
]


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


_NORM_PUNCT_RE = re.compile(r'[\s_/.\-~]+')
_NORM_DIGIT_LETTER_RE = re.compile(r'(\d)([A-Za-z])')
_NORM_DUP_SUFFIX_TOKEN_LEN = 2


def _normalise(text: str) -> str:
    """
    Canonicalise a regulation_number / filename stem for loose matching.

    Maps `01_PMK_010_2011_1.pdf` (file stem) and `01/PMK.010/2011`
    (metadata key) to the same form `01 PMK 010 2011`. Treats `_ / . - ~`
    and whitespace as separators; inserts a space between a digit and a
    following letter (`PP 7TAHUN 1977` → `PP 7 TAHUN 1977`); strips a
    trailing 1-2 digit token when at least 5 tokens remain, to drop the
    scraper's `_1` duplicate-copy suffix without clipping a legitimate
    trailing year.
    """
    s = _NORM_PUNCT_RE.sub(' ', text)
    s = _NORM_DIGIT_LETTER_RE.sub(r'\1 \2', s)
    tokens = s.strip().upper().split(' ')
    if (
        len(tokens) >= 5
        and tokens[-1].isdigit()
        and len(tokens[-1]) <= _NORM_DUP_SUFFIX_TOKEN_LEN
    ):
        tokens = tokens[:-1]
    return ' '.join(tokens)


_DUP_SUFFIX_RE = re.compile(r'_\d{1,2}$')


def _clean_article_number(num: str) -> str:
    """Uppercase and coerce OCR `O` → `0` in article numbers.

    Indonesian Pasal numbers use trailing letter suffixes (A, B, C, ...)
    for inserted articles but never `O` — OCR pipelines reliably mis-read
    a digit `0` as the letter `O`, producing `1O`, `10O`, etc.
    Coercing globally is safe because no legitimate suffix uses `O`.
    """
    return num.strip().upper().replace('O', '0')


def _pick_best_file(group: list[Path]) -> Path:
    """Tie-break duplicate files for the same regulation key.

    Order: PDF before HTML, original before `_N` duplicate copy, then
    lexical filename for a stable result.
    """
    def rank(p: Path) -> tuple[int, int, str]:
        fmt_rank = 0 if p.suffix.lower() == ".pdf" else 1
        dup_rank = 1 if _DUP_SUFFIX_RE.search(p.stem) else 0
        return (fmt_rank, dup_rank, p.name)
    return min(group, key=rank)


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


def _normalise_reg_type(raw: str) -> str:
    t = raw.lower().strip()
    for keyword, code in _REG_TYPE_NORMALISE:
        if keyword in t:
            return code
    return raw.upper()


def _extract_references(article_text: str, self_number: str) -> list[dict[str, str | None]]:
    """
    Intra-regulation references: 'Pasal N [ayat (M)]' mentions within the same regulation.
    Excludes self-references and any that are actually cross-regulation refs.
    Distinct (article, ayat) pairs are kept separately, so 'Pasal 4 ayat (1)' and
    'Pasal 4 ayat (2)' produce two entries.
    """
    cross_spans = {m.start() for m in CROSS_REG_REF_RE.finditer(article_text)}

    found: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for m in CROSS_REF_RE.finditer(article_text):
        if m.start() in cross_spans:
            continue
        article_num = _clean_article_number(m.group(1))
        ayat = m.group(2)
        if article_num == _clean_article_number(self_number):
            continue
        key = (article_num, ayat)
        if key in seen:
            continue
        found.append({"article": article_num, "ayat": ayat})
        seen.add(key)
    return found


def _extract_cross_reg_references(
    article_text: str,
    self_regulation_id: str,
) -> list[dict[str, str | None]]:
    """
    Inter-regulation references: 'Pasal N [ayat (M)] <RegType> Nomor X Tahun YYYY'.
    Returns list of {regulation_id, article_number, ayat} dicts, excluding
    references back to the same regulation. Distinct ayat values for the same
    target Pasal are kept as separate entries.
    """
    found: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for m in CROSS_REG_REF_RE.finditer(article_text):
        article_num = _clean_article_number(m.group(1))
        ayat        = m.group(2)
        reg_type    = _normalise_reg_type(m.group(3))
        reg_number  = m.group(4)
        year        = m.group(5)
        target_id   = f"{reg_type} {reg_number} TAHUN {year}"

        if target_id.upper() == self_regulation_id.upper():
            continue
        key = (target_id, article_num, ayat)
        if key in seen:
            continue
        found.append({
            "regulation_id": target_id,
            "article_number": article_num,
            "ayat": ayat,
        })
        seen.add(key)
    return found


def _extract_amends_from_title(title: str) -> list[dict[str, str]]:
    """
    Detect amendment / repeal relationships encoded in the regulation TITLE.
    Returns at most one entry of the form
        {"regulation_id": "<TYPE> <num> TAHUN <year>", "action": "amends"|"repeals"}
    or [] when the title is not an amendment/repeal.
    """
    m = AMENDS_PREFIX_RE.match(title)
    if not m:
        return []
    action = "repeals" if m.group("action").lower().lstrip().startswith("pencabutan") else "amends"
    ref = TITLE_REG_REF_RE.search(title[m.end():])
    if not ref:
        return []
    reg_type = _normalise_reg_type(ref.group(1))
    number   = ref.group(2)
    year     = ref.group(3) or ref.group(4)
    return [{
        "regulation_id": f"{reg_type} {number} TAHUN {year}",
        "action": action,
    }]


def _looks_definitional(article_number: str, content: str) -> bool:
    """
    True if this article reads like the canonical Pasal 1 definitions list.
    We require BOTH the article number to be '1' and the lead-in phrase
    'yang dimaksud dengan' to be present, to avoid extracting from
    non-definitional articles that happen to use 'adalah' in prose.
    """
    return article_number.upper() == "1" and "yang dimaksud dengan" in content.lower()


def _extract_definitions(article_text: str) -> list[str]:
    """
    Return the distinct defined Terms from a Pasal 1 article (in order of first
    appearance). Whitespace is collapsed first so the regex tolerates the
    line-break artefacts left by PDF text extraction.
    """
    normalised = re.sub(r'\s+', ' ', article_text)
    seen: set[str] = set()
    terms: list[str] = []
    for m in DEFINITION_RE.finditer(normalised):
        term = m.group("term").strip()
        # Reject very short tokens (formula variables like 'F1') and tokens
        # with no alphabetic character.
        if len(term) < 3 or not any(c.isalpha() for c in term):
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


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
        article_number: str = _clean_article_number(parts[i])
        raw_text: str = parts[i + 1]

        refs       = _extract_references(raw_text, article_number)
        cross_refs = _extract_cross_reg_references(raw_text, regulation_id)
        cleaned    = _clean(raw_text)
        defines    = _extract_definitions(cleaned) if _looks_definitional(article_number, cleaned) else []

        articles.append(
            {
                "regulation_id": regulation_id,
                "article_number": article_number,
                "content": cleaned,
                "raw_text": raw_text,
                "references": refs,
                "cross_regulation_references": cross_refs,
                "defines": defines,
                "source_format": "pdf",
            }
        )

    return articles


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------
def _extract_html_text(html_path: Path) -> str:
    """Extract plain text from an HTML regulation file using BeautifulSoup."""
    # Try UTF-8 first; fall back to latin-1 for old 1990s/2000s documents
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(html_path, encoding=encoding, errors="strict") as fh:
                raw = fh.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        with open(html_path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def parse_html(html_path: Path, regulation_id: str) -> list[dict]:
    """
    Extract text from *html_path*, split into Pasal units, detect cross-references.
    Returns the same article dict structure as parse_pdf.
    """
    full_text = _extract_html_text(html_path)
    parts = ARTICLE_HEADER_RE.split(full_text)

    articles: list[dict] = []
    for i in range(1, len(parts) - 1, 2):
        article_number: str = _clean_article_number(parts[i])
        raw_text: str = parts[i + 1]
        refs       = _extract_references(raw_text, article_number)
        cross_refs = _extract_cross_reg_references(raw_text, regulation_id)
        cleaned    = _clean(raw_text)
        defines    = _extract_definitions(cleaned) if _looks_definitional(article_number, cleaned) else []
        articles.append(
            {
                "regulation_id": regulation_id,
                "article_number": article_number,
                "content": cleaned,
                "raw_text": raw_text,
                "references": refs,
                "cross_regulation_references": cross_refs,
                "defines": defines,
                "source_format": "html",
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
    regulations_output_path: str = REGULATIONS_OUTPUT_JSON,
    limit: int | None = TEST_LIMIT,
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    metadata = _load_metadata(metadata_path)

    raw_dir = Path(pdf_dir)
    all_files = sorted(
        list(raw_dir.glob("*.pdf")) +
        list(raw_dir.glob("*.html")) +
        list(raw_dir.glob("*.htm"))
    )

    if not all_files:
        logger.error("No supported files found in '%s'.", pdf_dir)
        return

    pre_dedup_count = len(all_files)
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in all_files:
        groups[_normalise(f.stem)].append(f)
    all_files = sorted(_pick_best_file(g) for g in groups.values())
    logger.info(
        "File dedup: %d → %d unique regulation keys (%d duplicates dropped).",
        pre_dedup_count, len(all_files), pre_dedup_count - len(all_files),
    )

    if limit is not None:
        all_files = all_files[:limit]
        logger.info("TEST_LIMIT=%d — processing %d file(s).", limit, len(all_files))

    logger.info("Found %d file(s) to process (%d PDFs, %d HTML).",
                len(all_files),
                sum(1 for f in all_files if f.suffix.lower() == ".pdf"),
                sum(1 for f in all_files if f.suffix.lower() in (".html", ".htm")))

    all_articles: list[dict] = []
    all_regulations: list[dict] = []

    for file_path in all_files:
        stem_normalised = _normalise(file_path.stem)
        meta = metadata.get(stem_normalised)

        if meta is None:
            logger.warning(
                "No metadata entry for '%s' (normalised: '%s') — skipping.",
                file_path.name, stem_normalised,
            )
            continue

        regulation_id: str = meta["regulation_number"]
        fmt = file_path.suffix.lower().lstrip(".")
        logger.info("Parsing [%s] '%s'  →  regulation_id='%s'",
                    fmt.upper(), file_path.name, regulation_id)

        try:
            if fmt == "pdf":
                articles = parse_pdf(file_path, regulation_id)
            else:
                articles = parse_html(file_path, regulation_id)
        except ValueError as exc:
            logger.error("[IMAGE-ONLY] %s", exc)
            continue
        except Exception as exc:
            logger.error("Unexpected error parsing '%s': %s", file_path.name, exc)
            continue

        if not articles:
            logger.warning("  No Pasal found in '%s' — may be a preamble-only document.", file_path.name)
            continue

        amends = _extract_amends_from_title(meta.get("title", ""))
        all_regulations.append({
            "regulation_id":     regulation_id,
            "title":             meta.get("title", ""),
            "category":          meta.get("category", ""),
            "year":              meta.get("year", ""),
            "date_enacted":      meta.get("date_enacted", ""),
            "date_promulgated":  meta.get("date_promulgated", ""),
            "amends":            amends,
        })

        logger.info(
            "  Extracted %d articles, %d intra-refs, %d cross-reg refs, %d defined concepts, amends=%s.",
            len(articles),
            sum(len(a["references"]) for a in articles),
            sum(len(a["cross_regulation_references"]) for a in articles),
            sum(len(a.get("defines", [])) for a in articles),
            amends or "none",
        )
        all_articles.extend(articles)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(all_articles, fh, indent=2, ensure_ascii=False)

    os.makedirs(os.path.dirname(regulations_output_path), exist_ok=True)
    with open(regulations_output_path, "w", encoding="utf-8") as fh:
        json.dump(all_regulations, fh, indent=2, ensure_ascii=False)

    logger.info(
        "Done. %d articles → '%s';  %d regulations → '%s'.",
        len(all_articles), output_path,
        len(all_regulations), regulations_output_path,
    )


if __name__ == "__main__":
    parse_all()
