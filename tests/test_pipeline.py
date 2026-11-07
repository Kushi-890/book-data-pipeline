"""Offline tests: no internet needed. Run with:  python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import prepare_dataset as prep  # noqa: E402
import scrape_books as scr  # noqa: E402

LISTING_HTML = """
<ol><li><article class="product_pod">
  <p class="star-rating Three"></p>
  <h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light in ...</a></h3>
  <p class="price_color">£51.77</p></article></li></ol>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul>
"""

DETAIL_HTML = """
<ul class="breadcrumb"><li>Home</li><li>Books</li><li>Poetry</li><li>A Light in the Attic</li></ul>
<div id="product_description" class="sub-header"><h2>Product Description</h2></div>
<p>It's hard to imagine a world without A Light in the Attic.</p>
<table class="table table-striped">
<tr><th>UPC</th><td>a897fe39b1053632</td></tr>
<tr><th>Price (excl. tax)</th><td>£51.77</td></tr>
<tr><th>Availability</th><td>In stock (22 available)</td></tr>
<tr><th>Number of reviews</th><td>0</td></tr></table>
"""


class ParserTests(unittest.TestCase):
    def test_listing(self):
        books, next_url = scr.parse_listing(BeautifulSoup(LISTING_HTML, "html.parser"),
                                            "https://books.toscrape.com/catalogue/page-1.html")
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["title"], "A Light in the Attic")
        self.assertEqual(books[0]["rating_text"], "Three")
        self.assertEqual(books[0]["detail_url"],
                         "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
        self.assertEqual(next_url, "https://books.toscrape.com/catalogue/page-2.html")

    def test_detail(self):
        d = scr.parse_detail(BeautifulSoup(DETAIL_HTML, "html.parser"), "u")
        self.assertEqual(d["category"], "Poetry")
        self.assertEqual(d["upc"], "a897fe39b1053632")
        self.assertIn("A Light in the Attic", d["description"])


def make_raw():
    rows = []
    for i in range(30):
        rows.append({"title": f"Book {i}", "upc": f"upc{i}", "category": "Poetry" if i % 2 else "Travel",
                     "price_text": f"£{10 + i}.50", "rating_text": ["One", "Two", "Three", "Four", "Five"][i % 5],
                     "availability_text": "In stock (5 available)", "num_reviews_text": "0",
                     "description": "text" if i % 7 else "", "source_url": f"https://x/{i}"})
    rows.append(dict(rows[0]))                                   # exact duplicate
    rows.append({**rows[1], "title": "Dup upc"})                  # duplicate UPC
    rows.append({**rows[2], "upc": "bad1", "title": "No price", "price_text": ""})   # incomplete
    rows.append({**rows[3], "upc": "bad2", "title": "Bad rating", "rating_text": "Nine"})  # inconsistent
    return pd.DataFrame(rows)


class PrepareTests(unittest.TestCase):
    def test_clean_annotate_split(self):
        df, report = prep.clean(make_raw())
        self.assertEqual(len(df), 30)
        self.assertEqual(report["removed_duplicates"], 2)
        self.assertEqual(report["removed_incomplete"] + report["removed_inconsistent"], 2)
        df, edges = prep.annotate(df)
        prep.validate(df)
        self.assertEqual(len(edges), 4)
        parts = prep.split(df)
        self.assertEqual(sum(len(p) for p in parts.values()), 30)
        self.assertFalse(set(parts["train"]["upc"]) & set(parts["test"]["upc"]))


if __name__ == "__main__":
    unittest.main()
