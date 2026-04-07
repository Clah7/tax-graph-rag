import os
import json
import time
import random
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- Configuration ---
TARGET_URL = "https://jdih.kemenkeu.go.id/in/dokumen/peraturan" # Replace with specific search/filter URL
BASE_URL = "https://jdih.kemenkeu.go.id"
JSON_OUTPUT = "metadata.json"
PDF_DIR = "data/raw_pdfs"
MAX_PAGES = 5  

# --- Selectors (Must be verified against the live target DOM) ---
ROW_SELECTOR = "table tbody tr"
TITLE_SEL = "td:nth-child(2)" 
NOMOR_SEL = "td:nth-child(3)"
TAHUN_SEL = "td:nth-child(4)"
JENIS_SEL = "td:nth-child(5)"
STATUS_SEL = "td:nth-child(6)"
LINK_SEL = "td:nth-child(7) a"
NEXT_BTN_SEL = "a.next.page-numbers, button.next"

def setup_directories():
    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR)

def random_delay(min_sec=1.0, max_sec=3.0):
    time.sleep(random.uniform(min_sec, max_sec))

def download_pdf(url, filename):
    """Downloads PDF using requests with standard headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    filepath = os.path.join(PDF_DIR, filename)
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[+] Downloaded: {filename}")
    except requests.exceptions.RequestException as e:
        print(f"[-] Failed to download {url}: {e}")

def scrape_data():
    setup_directories()
    metadata = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        try:
            print(f"Navigating to {TARGET_URL}...")
            page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            print("[-] Timeout loading the initial page.")
            browser.close()
            return

        for current_page in range(1, MAX_PAGES + 1):
            print(f"Scraping Page {current_page}...")
            try:
                # Wait for the table rows to be visible
                page.wait_for_selector(ROW_SELECTOR, timeout=10000)
            except PlaywrightTimeoutError:
                print(f"[-] No data rows found on page {current_page}. Exiting loop.")
                break

            rows = page.locator(ROW_SELECTOR).all()
            for row in rows:
                try:
                    title = row.locator(TITLE_SEL).inner_text(timeout=2000).strip()
                    nomor = row.locator(NOMOR_SEL).inner_text(timeout=2000).strip()
                    tahun = row.locator(TAHUN_SEL).inner_text(timeout=2000).strip()
                    jenis = row.locator(JENIS_SEL).inner_text(timeout=2000).strip()
                    status = row.locator(STATUS_SEL).inner_text(timeout=2000).strip()
                    
                    link_locator = row.locator(LINK_SEL)
                    href = link_locator.get_attribute("href") if link_locator.count() > 0 else None
                    
                    pdf_url = urljoin(BASE_URL, href) if href else None

                    item = {
                        "title": title,
                        "regulation_number": nomor,
                        "year": tahun,
                        "category": jenis,
                        "status": status,
                        "url": pdf_url
                    }
                    metadata.append(item)

                    if pdf_url:
                        safe_filename = f"{jenis.replace(' ', '_')}_{nomor.replace('/', '_')}_{tahun}.pdf"
                        download_pdf(pdf_url, safe_filename)

                except Exception as e:
                    print(f"[-] Error parsing a row: {e}")
                    continue

            # Check for pagination
            next_button = page.locator(NEXT_BTN_SEL)
            if next_button.count() > 0 and next_button.is_visible() and next_button.is_enabled():
                print("Navigating to next page...")
                try:
                    next_button.click()
                    random_delay()
                    page.wait_for_load_state("networkidle")
                except Exception as e:
                    print(f"[-] Failed to navigate to next page: {e}")
                    break
            else:
                print("No more pages found.")
                break

            random_delay(1.5, 3.5)

        browser.close()

    # Save Metadata
    with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
    print(f"\n[+] Scraping complete. Metadata saved to {JSON_OUTPUT}")

if __name__ == "__main__":
    scrape_data()