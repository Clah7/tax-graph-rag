import json
import time
import random
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- Configuration ---
BASE_URL = "https://datacenter.ortax.org"
TARGET_URL = f"{BASE_URL}/ortax/aturan"
JSON_OUTPUT = "ortax_national_metadata.json"
MAX_PAGES = 5  # Adjust as needed for your full extraction

# --- Selectors ---
# Target specific national-level regulations
NATIONAL_TYPES = [
    "input[value='UU']", 
    "input[value='PP']", 
    "input[value='PMK']", 
    "input[value='PER_DJP']",
    "input[value='SE_DJP']"
]

# Escaped Tailwind CSS class for the repeating data cards
ROW_SEL = "div.\\@container\\/item"

def random_delay(min_sec=1.5, max_sec=3.5):
    """Prevents rate-limiting by simulating human delay."""
    time.sleep(random.uniform(min_sec, max_sec))

def scrape_ortax():
    metadata = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        try:
            print(f"[+] Navigating to {TARGET_URL}")
            page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            print("[-] Timeout loading the initial page.")
            browser.close()
            return

        print("[+] Applying national-level filters...")
        try:
            # --- NEW STEP: Open Advanced Search ---
            print("    -> Opening Advanced Search menu...")
            
            advanced_search_btn = page.get_by_role("button", name="Advance Search")
            advanced_search_btn.wait_for(state="visible", timeout=10000)
            advanced_search_btn.click()
            
            time.sleep(1) 
            # --------------------------------------

            # Now interact with the checkboxes
            for doc_type in NATIONAL_TYPES:
                if page.locator(doc_type).count() > 0:
                    page.locator(doc_type).check(force=True)
            
            # Execute search
            print("    -> Clicking Cari...")
            search_btn = page.locator("button:has-text('Cari')").first
            search_btn.wait_for(state="visible", timeout=15000)
            search_btn.click()
            
            page.wait_for_load_state("networkidle")
            random_delay()
            
        except Exception as e:
            print(f"[-] Error interacting with search form: {e}")
            browser.close()
            return

        # 2. Extract Data & Paginate
        for current_page in range(1, MAX_PAGES + 1):
            print(f"[+] Scraping Page {current_page}...")
            
            try:
                # Wait for the data cards to render
                page.wait_for_selector(ROW_SEL, timeout=10000)
            except PlaywrightTimeoutError:
                print(f"[-] No data rows found on page {current_page}. Exiting.")
                break

            rows = page.locator(ROW_SEL).all()
            for row in rows:
                try:
                    # URL Extraction
                    link_loc = row.locator("a").first
                    href = link_loc.get_attribute("href") if link_loc.count() > 0 else None
                    full_url = urljoin(BASE_URL, href) if href else None

                    # Title & Number
                    title_nomor = row.locator("h5").inner_text(timeout=2000).strip()

                    # Description
                    description = row.locator("p").inner_text(timeout=2000).strip()

                    # Date (Adjacent sibling to the calendar SVG)
                    date_text = row.locator("svg.lucide-calendar + div").inner_text(timeout=2000).strip()

                    # Category (Adjacent sibling to the folder SVG)
                    category = row.locator("svg.lucide-folder-closed + div").inner_text(timeout=2000).strip()

                    item = {
                        "regulation": title_nomor,
                        "description": description,
                        "date": date_text,
                        "category": category,
                        "url": full_url
                    }
                    metadata.append(item)

                except Exception as e:
                    print(f"[-] Error parsing an individual row: {e}")
                    continue

            # 3. Pagination Logic
            # Target the last button in the Mantine pagination group
            next_button = page.locator("div.mantine-Pagination-root button.mantine-Pagination-control").last
            
            if next_button.is_visible() and next_button.get_attribute("data-disabled") != "true":
                print("[+] Navigating to next page...")
                try:
                    next_button.click()
                    page.wait_for_load_state("networkidle")
                    random_delay(1.5, 3.5)
                except Exception as e:
                    print(f"[-] Failed to click next page: {e}")
                    break
            else:
                print("[+] End of pagination reached.")
                break

        browser.close()

    # 4. Save Output
    with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
    print(f"\n[+] Scraping complete. Metadata saved to {JSON_OUTPUT}")

if __name__ == "__main__":
    scrape_ortax()