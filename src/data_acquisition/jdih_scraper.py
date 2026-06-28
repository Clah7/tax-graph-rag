import json
import logging
import os
import random
import re
import time
from urllib.parse import urljoin

import requests
from playwright.sync_api import Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

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
BASE_URL: str = "https://jdih.kemenkeu.go.id"
TARGET_URL: str = (
    "https://jdih.kemenkeu.go.id/search"
    "?teu=Kementerian+Keuangan"
    "&bentuk=Peraturan+Menteri"
    "&order=desc"
    "&bentuk=Undang-Undang"
    "&bentuk=Peraturan+Pemerintah"
    "&bentuk=Peraturan+Pemerintah+Pengganti+Undang-Undang"
    "&bentuk=Peraturan+Unit+Eselon+I"
    "&teu=Indonesia"
    "&teu=Direktorat+Jenderal+Pajak"
    "&bentuk=Keputusan+Unit+Eselon+I"
)
JSON_OUTPUT: str = "data/jdih_metadata.json"
PDF_DIR: str = "data/raw_pdfs"
MAX_PAGES: int = 9999  # Runs until pagination is exhausted

# ---------------------------------------------------------------------------
# Selectors (verified against live DOM — card-based layout, not a table)
# ---------------------------------------------------------------------------
ROW_SEL: str = "div.jdih-search"
REGULATION_NUMBER_SEL: str = "h5.item a"     # text: "PMK 18 TAHUN 2026"
DETAIL_LINK_SEL: str = "h5.item a"           # href: "/dok/pmk-18-tahun-2026"
DESCRIPTION_SEL: str = "p.item"
CATEGORY_SEL: str = "div.search-label.item"  # topic labels, e.g. "PAJAK | KEUANGAN NEGARA"
DATES_SEL: str = "ul.search-meta li"         # [0] Ditetapkan, [1] Diundangkan
NEXT_BTN_SEL: str = "ul.jdih-pagination li.page-items:last-child a.page-links"

# Download links on detail pages: /api/download/{uuid}/{filename}.{ext}
# The extension may be pdf, html, htm, doc, docx — we match any download link.
_DOWNLOAD_RE: re.Pattern[str] = re.compile(r'/api/download/[^"\'<>\s]+', re.IGNORECASE)

_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
    "text/plain": ".txt",
}

_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _setup_directories() -> None:
    os.makedirs(PDF_DIR, exist_ok=True)


def _random_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def _clean_date(raw: str) -> str:
    """Strip Indonesian date prefixes and non-breaking spaces."""
    return (
        raw.replace("Ditetapkan:\xa0", "")
           .replace("Diundangkan:\xa0", "")
           .replace("Ditetapkan:", "")
           .replace("Diundangkan:", "")
           .strip()
    )


def _safe_basename(regulation_number: str) -> str:
    """Return a filesystem-safe base name (no extension)."""
    return re.sub(r'[^\w\-]', '_', regulation_number)


def _get_download_urls(detail_url: str) -> list[str]:
    """Return all /api/download/ URLs found on the detail page."""
    try:
        resp = requests.get(detail_url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        matches = _DOWNLOAD_RE.findall(resp.text)
        unique = list(dict.fromkeys(matches))  # deduplicate, preserve order
        return [urljoin(BASE_URL, m) for m in unique]
    except requests.exceptions.RequestException as exc:
        logger.warning("Could not fetch detail page %s: %s", detail_url, exc)
        return []


def _detect_file_info(url: str) -> tuple[str, str]:
    """
    Do a HEAD request to determine Content-Type and return (file_type, extension).
    Falls back to guessing from the URL path if the header is missing.
    """
    try:
        resp = requests.head(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = _CONTENT_TYPE_TO_EXT.get(content_type)
        if ext:
            return content_type, ext
    except requests.exceptions.RequestException:
        pass

    # Fallback: guess from URL extension
    url_lower = url.lower()
    for suffix, ext in [(".pdf", ".pdf"), (".html", ".html"), (".htm", ".html"),
                         (".docx", ".docx"), (".doc", ".doc"), (".txt", ".txt")]:
        if url_lower.endswith(suffix):
            return suffix.lstrip("."), ext

    return "unknown", ".bin"


def _already_downloaded(basename: str, ext: str) -> bool:
    """Return True if a file with this basename+ext already exists in PDF_DIR."""
    filepath = os.path.join(PDF_DIR, basename + ext)
    return os.path.isfile(filepath)


def _download_document(url: str, filename: str) -> str | None:
    """
    Stream *url* to PDF_DIR/<filename>.  Returns the local filepath on success.
    Skips download if the file already exists.
    """
    filepath = os.path.join(PDF_DIR, filename)
    if os.path.isfile(filepath):
        logger.info("Already downloaded, skipping: %s", filename)
        return filepath
    try:
        resp = requests.get(url, headers=_HEADERS, stream=True, timeout=60)
        resp.raise_for_status()
        with open(filepath, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
        logger.info("Downloaded: %s", filename)
        return filepath
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to download %s — %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Row extraction
# ---------------------------------------------------------------------------
def _extract_row(card, base_url: str) -> dict[str, str | None] | None:
    """
    Extract metadata from a single div.jdih-search card.
    Returns None on failure so the caller can skip gracefully.
    """
    try:
        regulation_number: str = (
            card.locator(REGULATION_NUMBER_SEL).inner_text(timeout=2000).strip()
        )
        description: str = card.locator(DESCRIPTION_SEL).inner_text(timeout=2000).strip()
        category: str = card.locator(CATEGORY_SEL).inner_text(timeout=2000).strip()

        href: str | None = card.locator(DETAIL_LINK_SEL).get_attribute("href")
        detail_url: str | None = urljoin(base_url, href) if href else None

        # Year is encoded in the regulation number: "PMK 18 TAHUN 2026"
        year_match = re.search(r'TAHUN\s+(\d{4})', regulation_number, re.IGNORECASE)
        year: str | None = year_match.group(1) if year_match else None

        # Date metadata: first li = Ditetapkan, second = Diundangkan
        date_lis = card.locator(DATES_SEL).all()
        date_enacted: str | None = (
            _clean_date(date_lis[0].inner_text(timeout=1000)) if date_lis else None
        )
        date_promulgated: str | None = (
            _clean_date(date_lis[1].inner_text(timeout=1000)) if len(date_lis) > 1 else None
        )

        return {
            "regulation_number": regulation_number,
            "title": description,
            "year": year,
            "category": category,
            "date_enacted": date_enacted,
            "date_promulgated": date_promulgated,
            "detail_url": detail_url,
        }
    except Exception as exc:
        logger.warning("Skipping card due to parse error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Page scraping
# ---------------------------------------------------------------------------
def _scrape_page(page: Page, page_num: int) -> list[dict[str, str | None]]:
    """Wait for cards to appear then extract and enrich every card on the page."""
    logger.info("Scraping page %d…", page_num)
    try:
        page.wait_for_selector(ROW_SEL, timeout=15000)
    except PlaywrightTimeoutError:
        logger.warning("No result cards found on page %d — stopping.", page_num)
        return []

    cards = page.locator(ROW_SEL).all()
    records: list[dict[str, str | None]] = []

    for card in cards:
        record = _extract_row(card, BASE_URL)
        if record is None:
            continue

        # Resolve download URLs and detect file types
        record["documents"] = []
        if record["detail_url"]:
            download_urls = _get_download_urls(record["detail_url"])
            basename = _safe_basename(record["regulation_number"])
            for i, dl_url in enumerate(download_urls):
                file_type, ext = _detect_file_info(dl_url)
                suffix = f"_{i}" if i > 0 else ""
                filename = basename + suffix + ext
                if not _already_downloaded(basename + suffix, ext):
                    local_path = _download_document(dl_url, filename)
                else:
                    local_path = os.path.join(PDF_DIR, filename)
                    logger.info("Already downloaded, skipping: %s", filename)
                record["documents"].append({
                    "url": dl_url,
                    "file_type": file_type,
                    "extension": ext,
                    "filename": filename,
                    "local_path": local_path,
                })

        records.append(record)
        _random_delay(0.5, 1.5)  # Courtesy delay between detail-page requests

    logger.info("Page %d — extracted %d records.", page_num, len(records))
    return records


def _go_to_next_page(page: Page) -> bool:
    """Click the next-page arrow. Returns False when pagination is exhausted."""
    next_btn = page.locator(NEXT_BTN_SEL)
    if next_btn.count() == 0:
        logger.info("Pagination element not found — done.")
        return False
    if next_btn.get_attribute("aria-disabled") == "true":
        logger.info("Next page button is disabled — pagination complete.")
        return False

    try:
        next_btn.click()
        page.wait_for_load_state("networkidle")
        _random_delay(1.5, 3.5)
        return True
    except Exception as exc:
        logger.error("Failed to navigate to next page: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def scrape_jdih() -> None:
    _setup_directories()
    metadata: list[dict[str, str | None]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=_HEADERS["User-Agent"],
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        logger.info("Navigating to %s", TARGET_URL)
        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            logger.error("Timeout loading the initial page. Aborting.")
            browser.close()
            return

        for current_page in range(1, MAX_PAGES + 1):
            page_records = _scrape_page(page, current_page)
            metadata.extend(page_records)

            if not page_records:
                break

            if not _go_to_next_page(page):
                break

        browser.close()

    with open(JSON_OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=4, ensure_ascii=False)

    logger.info(
        "Scraping complete. %d records saved to %s", len(metadata), JSON_OUTPUT
    )


if __name__ == "__main__":
    scrape_jdih()
