"""Contract and unit tests for models, normalization, deduplication, and export serialization."""

import csv
import json
import unittest
from decimal import Decimal
from pathlib import Path

from scraping_system.config import Settings
from scraping_system.exporters import export_records
from scraping_system.models import BookRecord, QuoteRecord, RunMetrics
from scraping_system.pipelines.deduplication import Deduplicator
from scraping_system.pipelines.normalization import (
    normalize_currency,
    normalize_url,
    normalize_whitespace,
    parse_price,
    parse_rating,
)
from scraping_system.pipelines.validation import ProcessingPipeline


class TestContractsAndModels(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(__file__).parent / "output"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for f in self.tmp_dir.glob("*"):
            if f.is_file():
                f.unlink()
        if self.tmp_dir.exists():
            self.tmp_dir.rmdir()

    def test_whitespace_normalization(self):
        dirty = "  This   is   a   \n\t messy string  "
        self.assertEqual(normalize_whitespace(dirty), "This is a messy string")

    def test_url_normalization(self):
        url = "https://books.toscrape.com/catalogue/category/books_1/index.html"
        self.assertEqual(normalize_url(url), url)
        with self.assertRaises(ValueError):
            normalize_url("ftp://example.com")
        with self.assertRaises(ValueError):
            normalize_url("")

    def test_parse_price_to_decimal(self):
        self.assertEqual(parse_price("£51.77"), Decimal("51.77"))
        self.assertEqual(parse_price("51.77"), Decimal("51.77"))
        self.assertEqual(parse_price("  £ 10.99 \n"), Decimal("10.99"))
        self.assertEqual(parse_price(Decimal("25.50")), Decimal("25.50"))
        with self.assertRaises(ValueError):
            parse_price("invalid")
        with self.assertRaises(ValueError):
            parse_price("-10.00")
        with self.assertRaises(ValueError):
            parse_price(True)

    def test_normalize_currency(self):
        self.assertEqual(normalize_currency("£"), "GBP")
        self.assertEqual(normalize_currency("GBP"), "GBP")
        self.assertEqual(normalize_currency("$"), "USD")
        self.assertEqual(normalize_currency("€"), "EUR")
        with self.assertRaises(ValueError):
            normalize_currency("XYZ")

    def test_parse_rating_conversions(self):
        self.assertEqual(parse_rating("One"), 1)
        self.assertEqual(parse_rating("TWO"), 2)
        self.assertEqual(parse_rating("Three"), 3)
        self.assertEqual(parse_rating("four"), 4)
        self.assertEqual(parse_rating("Five"), 5)
        self.assertEqual(parse_rating("star-rating Three"), 3)
        self.assertEqual(parse_rating(4), 4)

        with self.assertRaises(ValueError):
            parse_rating("Zero")
        with self.assertRaises(ValueError):
            parse_rating("Six")
        with self.assertRaises(ValueError):
            parse_rating(0)
        with self.assertRaises(ValueError):
            parse_rating(6)

    def test_book_record_validation(self):
        valid = {
            "title": "A Light in the Attic",
            "price": Decimal("51.77"),
            "currency": "GBP",
            "availability": "In stock",
            "rating": 3,
            "category": "Poetry",
            "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        }
        record = BookRecord.model_validate(valid)
        self.assertEqual(record.title, "A Light in the Attic")
        self.assertEqual(record.rating, 3)
        self.assertEqual(record.source, "books.toscrape.com")
        self.assertTrue(len(record.record_id) == 64)

        invalid = dict(valid)
        invalid["title"] = ""
        with self.assertRaises(ValueError):
            BookRecord.model_validate(invalid)

    def test_quote_record_validation(self):
        valid = {
            "quote": "The world as we have created it is a process of our thinking.",
            "author": "Albert Einstein",
            "tags": ["change", "thinking", "world"],
            "source_url": "https://quotes.toscrape.com/js/",
        }
        record = QuoteRecord.model_validate(valid)
        self.assertEqual(record.author, "Albert Einstein")
        self.assertEqual(record.source, "quotes.toscrape.com")
        self.assertEqual(len(record.record_id), 64)

        invalid = dict(valid)
        invalid["quote"] = "   "
        with self.assertRaises(ValueError):
            QuoteRecord.model_validate(invalid)

    def test_deduplicator(self):
        dedup = Deduplicator()
        self.assertFalse(dedup.is_duplicate("key-1"))
        self.assertTrue(dedup.is_duplicate("key-1"))
        self.assertFalse(dedup.is_duplicate("key-2"))
        self.assertEqual(len(dedup.seen), 2)

    def test_processing_pipeline_flow(self):
        metrics = RunMetrics(source="books.toscrape.com")
        pipeline = ProcessingPipeline(metrics)

        raw_valid = {
            "title": "A Light in the Attic",
            "price": "£51.77",
            "currency": "GBP",
            "availability": "In stock",
            "rating": "Three",
            "category": "Poetry",
            "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        }

        rec1 = pipeline.process(raw_valid, "books")
        self.assertIsNotNone(rec1)
        self.assertEqual(metrics.extracted, 1)
        self.assertEqual(metrics.accepted, 1)
        self.assertEqual(metrics.invalid, 0)
        self.assertEqual(metrics.duplicates, 0)
        self.assertEqual(len(pipeline.records), 1)

        rec2 = pipeline.process(raw_valid, "books")
        self.assertIsNone(rec2)
        self.assertEqual(metrics.extracted, 2)
        self.assertEqual(metrics.accepted, 1)
        self.assertEqual(metrics.duplicates, 1)

        raw_invalid = {
            "title": "",
            "price": "not-a-price",
            "rating": "InvalidRating",
            "product_url": "invalid-url",
        }
        rec3 = pipeline.process(raw_invalid, "books")
        self.assertIsNone(rec3)
        self.assertEqual(metrics.extracted, 3)
        self.assertEqual(metrics.invalid, 1)
        self.assertEqual(len(pipeline.rejected), 1)

    def test_settings_validation(self):
        settings = Settings(max_pages=3, delay=0.5, retries=1)
        self.assertEqual(settings.max_pages, 3)
        self.assertEqual(settings.delay, 0.5)
        self.assertTrue(settings.headless)

    def test_export_records_json(self):
        record = BookRecord.model_validate(
            {
                "title": "A Light in the Attic",
                "price": Decimal("51.77"),
                "currency": "GBP",
                "availability": "In stock",
                "rating": 3,
                "category": "Poetry",
                "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            }
        )
        metrics = RunMetrics(source="books")
        json_file = self.tmp_dir / "exported.json"
        res_path = export_records([record], format="json", destination=json_file, metrics=metrics)

        self.assertTrue(Path(res_path).exists())
        with open(res_path, encoding="utf-8") as f:
            loaded = json.load(f)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["title"], "A Light in the Attic")
        self.assertEqual(loaded[0]["rating"], 3)
        self.assertEqual(loaded[0]["price"], "51.77")

    def test_export_records_csv(self):
        record = BookRecord.model_validate(
            {
                "title": "A Light in the Attic, Volume 1",
                "price": Decimal("51.77"),
                "currency": "GBP",
                "availability": "In stock",
                "rating": 3,
                "category": "Poetry",
                "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            }
        )
        metrics = RunMetrics(source="books")
        csv_file = self.tmp_dir / "exported.csv"
        res_path = export_records([record], format="csv", destination=csv_file, metrics=metrics)

        self.assertTrue(Path(res_path).exists())
        with open(res_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "A Light in the Attic, Volume 1")
        self.assertEqual(rows[0]["price"], "51.77")
        self.assertEqual(rows[0]["rating"], "3")


if __name__ == "__main__":
    unittest.main()
