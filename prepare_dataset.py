"""Clean the raw scraped books, label them, split them and export model-ready files.

Usage:
    python prepare_dataset.py

Input:   data/raw/books_raw.jsonl
Output:  data/processed/{full,train,val,test}/books_<name>.{csv,jsonl,json}
         data/processed/data_quality_report.json
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

RAW_PATH = Path("data/raw/books_raw.jsonl")
OUT_DIR = Path("data/processed")
RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
REQUIRED = ["title", "upc", "category", "price", "rating"]
COLUMNS = ["upc", "title", "category", "price", "rating", "availability",
           "num_reviews", "description", "price_band", "rating_label", "source_url"]


def first_number(text):
    match = re.search(r"\d+", str(text))
    return int(match.group()) if match else 0


def clean(raw):
    """Standardise formats and remove bad records. Returns (clean_df, report)."""
    report = {"rows_raw": len(raw)}
    df = raw.copy()

    # 1. Trim whitespace in every text column and treat empty strings as missing
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].astype("string").str.strip().replace("", pd.NA)

    # 2. Standardise formats
    df["price"] = pd.to_numeric(df["price_text"].astype("string").str.replace(r"[^\d.]", "", regex=True), errors="coerce")
    df["rating"] = df["rating_text"].map(RATING_MAP)
    df["availability"] = df["availability_text"].map(first_number)
    df["num_reviews"] = df["num_reviews_text"].map(first_number)
    df["description"] = df["description"].fillna("")
    report["missing_description_kept_as_empty"] = int((df["description"] == "").sum())

    # 3. Remove incomplete records (a required field is missing)
    before = len(df)
    df = df.dropna(subset=REQUIRED)
    report["removed_incomplete"] = before - len(df)

    # 4. Remove inconsistent records (impossible values)
    before = len(df)
    df = df[(df["price"] > 0) & df["rating"].between(1, 5)]
    report["removed_inconsistent"] = before - len(df)

    # 5. Remove duplicates (the UPC is a unique product id)
    before = len(df)
    df = df.drop_duplicates(subset="upc").drop_duplicates(subset=["title", "price", "category"])
    report["removed_duplicates"] = before - len(df)

    df["rating"] = df["rating"].astype(int)
    return df.reset_index(drop=True), report


def annotate(df):
    """Add rule-based labels. Returns (labelled_df, price band edges)."""
    df = df.copy()
    df["price_band"], edges = pd.qcut(df["price"], 3, labels=["low", "medium", "high"], retbins=True, duplicates="drop")
    df["price_band"] = df["price_band"].astype(str)
    df["rating_label"] = df["rating"].map(lambda r: "low" if r <= 2 else "medium" if r == 3 else "high")
    return df, [round(float(e), 2) for e in edges]


def validate(df):
    """Quality checks: stop with a clear error if the final data breaks a rule."""
    assert df["upc"].is_unique, "duplicate UPCs found"
    assert not df[REQUIRED].isna().any().any(), "missing values in required columns"
    assert df["price"].gt(0).all(), "non-positive price found"
    assert df["rating"].between(1, 5).all(), "rating outside 1-5"
    assert set(df["price_band"]) <= {"low", "medium", "high"}, "unexpected price_band label"


def split(df, seed=42):
    """70 / 15 / 15 train / validation / test split, stratified by price_band when possible."""
    try:
        train, rest = train_test_split(df, test_size=0.30, random_state=seed, stratify=df["price_band"])
        val, test = train_test_split(rest, test_size=0.50, random_state=seed, stratify=rest["price_band"])
    except ValueError:  # a class is too small to stratify (very small scrapes)
        train, rest = train_test_split(df, test_size=0.30, random_state=seed)
        val, test = train_test_split(rest, test_size=0.50, random_state=seed)
    return {"train": train, "val": val, "test": test}


def export(df, name, out_dir):
    folder = out_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    df = df[COLUMNS]
    df.to_csv(folder / f"books_{name}.csv", index=False, encoding="utf-8")
    records = df.to_dict(orient="records")
    with (folder / f"books_{name}.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    (folder / f"books_{name}.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    raw = pd.read_json(args.raw, lines=True, dtype=False)
    df, report = clean(raw)
    df, band_edges = annotate(df)
    validate(df)
    parts = split(df)

    export(df, "full", args.out)
    for name, part in parts.items():
        export(part, name, args.out)

    report.update({
        "rows_final": len(df),
        "categories": int(df["category"].nunique()),
        "price_band_edges_gbp": band_edges,
        "price_band_counts": df["price_band"].value_counts().to_dict(),
        "split_sizes": {name: len(part) for name, part in parts.items()},
        "source": "https://books.toscrape.com/",
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    (args.out / "data_quality_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
