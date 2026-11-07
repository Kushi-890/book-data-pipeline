# Book Data Pipeline: web scraping to model-ready datasets

A small end-to-end data-collection project. It scrapes book data from a public practice website, cleans and validates it, adds labels, splits it into training, validation and test sets, and exports it as CSV, JSON and JSONL with a data-quality report.

**Tools:** Python, Requests, BeautifulSoup, Pandas, scikit-learn

## Data source

| Item | Detail |
|---|---|
| Website | https://books.toscrape.com/ |
| Why this site | It is a sandbox built for scraping practice, so scraping it is authorised |
| What is collected | Title, category, price, star rating, UPC, availability, number of reviews, description, page URL |
| Politeness | Custom User-Agent, 1 second delay between requests, retries with back-off, timeouts |

Every record keeps its `source_url` (and the raw file keeps a `scraped_at` timestamp), so each row can be traced back to its page.

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt

python scrape_books.py --pages 5      # 5 pages = about 100 books (use --pages 50 for all 1,000)
python prepare_dataset.py             # clean, label, split, export
python -m unittest discover tests     # offline tests, no internet needed
```

## Pipeline

1. **Collect** (`scrape_books.py`): follows the listing pages, opens each book page, parses the HTML and saves raw records to `data/raw/books_raw.jsonl`.
2. **Clean** (`prepare_dataset.py`):
   - trims whitespace and treats empty strings as missing
   - standardises formats: price `£51.77` to `51.77`, rating `Three` to `3`, `In stock (22 available)` to `22`
   - removes **incomplete** records (missing title, UPC, category, price or rating)
   - removes **inconsistent** records (price not above 0, rating outside 1 to 5)
   - removes **duplicate** records (same UPC, or same title + price + category)
3. **Annotate** (rule-based labels):
   - `price_band`: low / medium / high (three equal-sized groups by price)
   - `rating_label`: low (1 to 2 stars) / medium (3) / high (4 to 5)
4. **Validate**: the script stops with an error if the final data has duplicate UPCs, missing required values, bad prices or ratings, or unexpected labels.
5. **Split**: 70% train, 15% validation, 15% test, stratified by `price_band`, with a fixed random seed (42) so results can be reproduced.
6. **Export**: every dataset is written as CSV, JSON and JSONL.

## Output structure

```
data/
  raw/books_raw.jsonl                     scraped records, exactly as collected
  processed/
    full/   books_full.{csv,json,jsonl}   all clean records
    train/  books_train.{csv,json,jsonl}
    val/    books_val.{csv,json,jsonl}
    test/   books_test.{csv,json,jsonl}
    data_quality_report.json              row counts, removals, label counts, split sizes
```

## Schema

| Column | Type | Description |
|---|---|---|
| upc | string | Unique product code |
| title | string | Book title |
| category | string | Book category (e.g. Poetry) |
| price | float | Price in GBP |
| rating | int | Star rating, 1 to 5 |
| availability | int | Copies in stock |
| num_reviews | int | Number of reviews |
| description | string | Book description (empty if the page has none) |
| price_band | string | low / medium / high |
| rating_label | string | low / medium / high |
| source_url | string | Page the record was scraped from |

## Limitations

- The labels are rule-based, so they are not a substitute for human annotation.
- The site is a practice site with fake stock data, so the values are not real market data.
- The scraper expects the current HTML layout; if the site changes, the selectors in `parse_listing` and `parse_detail` need updating.

## Results

After you run the pipeline, copy the numbers from `data/processed/data_quality_report.json` here (rows scraped, records removed, final rows, split sizes).
