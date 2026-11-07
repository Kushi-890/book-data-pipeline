"""Scrape book listings and detail pages from books.toscrape.com.

books.toscrape.com is a sandbox site built for scraping practice, so scraping
it is authorised. The script is polite: it sends a User-Agent, waits between
requests, retries failed requests and never hammers the server.

Usage:
    python scrape_books.py --pages 5 --delay 1.0

Output:
    data/raw/books_raw.jsonl  (one JSON record per book, exactly as scraped)
"""
import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
START_URL = urljoin(BASE_URL, "catalogue/page-1.html")
HEADERS = {"User-Agent": "dataset-prep-practice-project/1.0 (educational use)"}
RAW_PATH = Path("data/raw/books_raw.jsonl")

log = logging.getLogger("scraper")


def fetch(session, url, retries=3, delay=1.0, timeout=15):
    """Download a page and return a BeautifulSoup object, or None if it keeps failing."""
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            response.encoding = "utf-8"  # the site is UTF-8 but is detected wrongly (GBP sign breaks)
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as err:
            log.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, err)
            time.sleep(delay * attempt)  # back off a little more each time
    log.error("Giving up on %s", url)
    return None


def parse_listing(soup, page_url):
    """Return (list of basic book info, absolute URL of the next page or None)."""
    books = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        rating = card.select_one("p.star-rating")
        books.append({
            "title": link.get("title", "").strip() if link else "",
            "detail_url": urljoin(page_url, link["href"]) if link and link.get("href") else "",
            "price_text": card.select_one("p.price_color").get_text(strip=True) if card.select_one("p.price_color") else "",
            # the rating is stored as a CSS class, e.g. class="star-rating Three"
            "rating_text": next((c for c in rating.get("class", []) if c != "star-rating"), "") if rating else "",
        })
    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return books, next_url


def parse_detail(soup, url):
    """Pull category, UPC, availability, reviews and description from a book page."""
    crumbs = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
    table = {
        row.th.get_text(strip=True): row.td.get_text(strip=True)
        for row in soup.select("table.table-striped tr")
        if row.th and row.td
    }
    description_header = soup.select_one("#product_description")
    description = ""
    if description_header:
        paragraph = description_header.find_next_sibling("p")
        description = paragraph.get_text(strip=True) if paragraph else ""
    return {
        "category": crumbs[2] if len(crumbs) > 2 else "",
        "upc": table.get("UPC", ""),
        "price_excl_tax_text": table.get("Price (excl. tax)", ""),
        "availability_text": table.get("Availability", ""),
        "num_reviews_text": table.get("Number of reviews", ""),
        "description": description,
        "source_url": url,
    }


def scrape(max_pages, delay):
    records = []
    session = requests.Session()
    url, page = START_URL, 1
    while url and page <= max_pages:
        log.info("Listing page %d: %s", page, url)
        soup = fetch(session, url, delay=delay)
        if soup is None:
            break
        books, next_url = parse_listing(soup, url)
        for book in books:
            time.sleep(delay)
            detail_soup = fetch(session, book["detail_url"], delay=delay)
            if detail_soup is None:
                continue  # skip books whose page could not be loaded
            record = {**book, **parse_detail(detail_soup, book["detail_url"])}
            record["scraped_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            records.append(record)
        url, page = next_url, page + 1
        time.sleep(delay)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, default=5, help="listing pages to scrape (20 books each, max 50)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds to wait between requests")
    parser.add_argument("--out", type=Path, default=RAW_PATH, help="raw output file (JSONL)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    records = scrape(args.pages, args.delay)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("Saved %d raw records to %s", len(records), args.out)


if __name__ == "__main__":
    main()
