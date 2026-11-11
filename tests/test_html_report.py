"""Unit tests for the HTML dashboard run report generator."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from scraping_system.reporting.html_report import (
    _format_elapsed,
    _render_stars,
    generate_report,
)


class MockRunMetrics:
    def __init__(
        self,
        run_id="run-1234-5678",
        source="quotes.toscrape.com",
        status="completed",
        pages_processed=3,
        extracted=30,
        accepted=28,
        invalid=1,
        duplicates=1,
        retries=1,
        elapsed_seconds=4.5,
        output_format="json",
        output_path="artifacts/quotes.json",
        errors=None,
    ):
        self.run_id = run_id
        self.source = source
        self.status = status
        self.started_at = datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC)
        self.finished_at = datetime(2026, 9, 21, 10, 0, 5, tzinfo=UTC)
        self.pages_processed = pages_processed
        self.extracted = extracted
        self.accepted = accepted
        self.invalid = invalid
        self.duplicates = duplicates
        self.retries = retries
        self.elapsed_seconds = elapsed_seconds
        self.output_format = output_format
        self.output_path = output_path
        self.errors = errors or []


class TestHtmlReport(unittest.TestCase):
    def setUp(self):
        self.test_output = Path(__file__).parent / "output" / "test_report.html"
        if self.test_output.exists():
            self.test_output.unlink()

    def tearDown(self):
        if self.test_output.exists():
            self.test_output.unlink()
        if self.test_output.parent.exists() and not any(self.test_output.parent.iterdir()):
            self.test_output.parent.rmdir()

    def test_generate_report_creates_file_and_directories(self):
        run = MockRunMetrics()
        dest = generate_report([run], [], self.test_output)

        self.assertTrue(dest.exists())
        self.assertEqual(dest, self.test_output)
        content = dest.read_text(encoding="utf-8")
        self.assertIn("Python Web Scraping & Data Extraction System", content)
        self.assertIn("Run Status: COMPLETED", content)

    def test_generate_report_aggregates_multiple_runs(self):
        run1 = MockRunMetrics(
            source="books.toscrape.com",
            pages_processed=2,
            extracted=40,
            accepted=38,
            invalid=1,
            duplicates=1,
            retries=0,
            elapsed_seconds=2.5,
        )
        run2 = MockRunMetrics(
            source="quotes.toscrape.com",
            pages_processed=3,
            extracted=30,
            accepted=27,
            invalid=2,
            duplicates=1,
            retries=2,
            elapsed_seconds=3.5,
        )

        dest = generate_report([run1, run2], [], self.test_output)
        content = dest.read_text(encoding="utf-8")

        self.assertIn(">5<", content)
        self.assertIn(">70<", content)
        self.assertIn(">65<", content)
        self.assertIn(">2<", content)

    def test_generate_report_renders_mixed_records(self):
        book_record = {
            "title": "A Light in the Attic",
            "price": Decimal("51.77"),
            "currency": "GBP",
            "availability": "In stock (22 available)",
            "rating": 3,
            "category": "Poetry",
            "product_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            "scraped_at": datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC),
        }
        quote_record = {
            "quote": "The world as we have created it is a process of our thinking.",
            "author": "Albert Einstein",
            "tags": ["change", "thinking"],
            "source_url": "https://quotes.toscrape.com/js/",
            "scraped_at": datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC),
        }

        run = MockRunMetrics()
        dest = generate_report([run], [book_record, quote_record], self.test_output)
        content = dest.read_text(encoding="utf-8")

        self.assertIn("Extracted Books Sample", content)
        self.assertIn("A Light in the Attic", content)
        self.assertIn("£51.77", content)
        self.assertIn("Poetry", content)

        self.assertIn("Extracted Quotes Sample", content)
        self.assertIn("The world as we have created it", content)
        self.assertIn("Albert Einstein", content)
        self.assertIn("change", content)

    def test_generate_report_escapes_scraped_text(self):
        malicious_quote = {
            "quote": "<script>alert('xss')</script> & 'quotes'",
            "author": "<img src=x onerror=alert(1)>",
            "tags": ["<script>", "normal"],
            "source_url": "https://quotes.toscrape.com/js/",
        }

        run = MockRunMetrics()
        dest = generate_report([run], [malicious_quote], self.test_output)
        content = dest.read_text(encoding="utf-8")

        self.assertNotIn("<script>alert('xss')</script>", content)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", content)
        self.assertNotIn("<img src=x onerror=alert(1)>", content)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", content)

    def test_generate_report_handles_empty_dataset(self):
        run = MockRunMetrics(extracted=0, accepted=0)
        dest = generate_report([run], [], self.test_output)
        content = dest.read_text(encoding="utf-8")

        self.assertIn("No Records Extracted", content)
        self.assertNotIn("Extracted Books Sample", content)
        self.assertNotIn("Extracted Quotes Sample", content)

    def test_generate_report_handles_failed_run_and_errors(self):
        run = MockRunMetrics(
            status="failed",
            errors=["Connection refused to Selenium grid", "HTTP 500 from server"],
        )
        dest = generate_report([run], [], self.test_output)
        content = dest.read_text(encoding="utf-8")

        self.assertIn("Run Status: FAILED", content)
        self.assertIn("Operational Warnings / Errors:", content)
        self.assertIn("Connection refused to Selenium grid", content)
        self.assertIn("HTTP 500 from server", content)

    def test_generate_report_has_no_external_cdn(self):
        run = MockRunMetrics()
        dest = generate_report([run], [], self.test_output)
        content = dest.read_text(encoding="utf-8")

        self.assertNotIn('<link rel="stylesheet" href="http', content)
        self.assertNotIn('<script src="http', content)

    def test_helper_render_stars(self):
        self.assertIn("★★★☆☆", _render_stars(3))
        self.assertIn("★☆☆☆☆", _render_stars(1))
        self.assertIn("★★★★★", _render_stars(5))
        self.assertIn("★★★★★", _render_stars(10))
        self.assertIn("★☆☆☆☆", _render_stars(0))

    def test_helper_format_elapsed(self):
        self.assertEqual(_format_elapsed(5.2), "5.20s")
        self.assertEqual(_format_elapsed(65.4), "1m 5.4s")
        self.assertEqual(_format_elapsed("invalid"), "N/A")


if __name__ == "__main__":
    unittest.main()
