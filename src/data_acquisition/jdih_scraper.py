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
JSON_OUTPUT: str = "jdih_metadata.json"
PDF_DIR: str = "data/raw_pdfs"
MAX_PAGES: int = 1  # Hardcoded for testing

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

# PDF links on detail pages follow this pattern:
# /api/download/{uuid}/{filename}.pdf
_PDF_RE: re.Pattern[str] = re.compile(r'/api/download/[^"\'<>\s]+\.pdf', re.IGNORECASE)

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


def _safe_filename(regulation_number: str) -> str:
    return re.sub(r'[^\w\-.]', '_', regulation_number) + ".pdf"


def _get_pdf_url(detail_url: str) -> str | None:
    """
    Fetch the regulation detail page with requests and extract the first
    /api/download/...pdf URL found in the HTML.
    Does NOT use Playwright — keeps browser sessions lean.
    """
    try:
        resp = requests.get(detail_url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        match = _PDF_RE.search(resp.text)
        if match:
            return urljoin(BASE_URL, match.group(0))
        logger.warning("No PDF link found on detail page: %s", detail_url)
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning("Could not fetch detail page %s: %s", detail_url, exc)
        return None


def _download_pdf(url: str, filename: str) -> None:
    """Stream a PDF from *url* to PDF_DIR/<filename> using requests."""
    filepath = os.path.join(PDF_DIR, filename)
    try:
        resp = requests.get(url, headers=_HEADERS, stream=True, timeout=30)
        resp.raise_for_status()
        with open(filepath, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
        logger.info("Downloaded: %s", filename)
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to download %s — %s", url, exc)


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

        # Resolve the actual PDF URL from the detail page (via requests, not Playwright)
        if record["detail_url"]:
            pdf_url = _get_pdf_url(record["detail_url"])
            record["pdf_url"] = pdf_url
            if pdf_url:
                _download_pdf(pdf_url, _safe_filename(record["regulation_number"]))
        else:
            record["pdf_url"] = None

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

            if current_page < MAX_PAGES:
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
