"""Stable CSV columns, JSON-encoded tag arrays, and spreadsheet-safe text."""

import csv
import json
from pathlib import Path

from scraping_system.models import BookRecord, QuoteRecord, Record
from scraping_system.utils.files import atomic_text

BOOK_FIELDS = [
    "title",
    "price",
    "currency",
    "availability",
    "rating",
    "category",
    "product_url",
    "source",
    "scraped_at",
]
QUOTE_FIELDS = ["quote", "author", "tags", "source_url", "source", "scraped_at"]


def export_csv(records: list[Record], destination: Path, kind: str = "books") -> Path:
    expected = BookRecord if kind == "books" else QuoteRecord
    if any(not isinstance(record, expected) for record in records):
        raise ValueError("CSV requires one record kind per file")
    fields = BOOK_FIELDS if kind == "books" else QUOTE_FIELDS
    with atomic_text(destination, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = record.model_dump(mode="json")
            if "tags" in row:
                row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
            for key, value in row.items():
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
                    row[key] = "'" + value
            writer.writerow(row)
    return Path(destination)
