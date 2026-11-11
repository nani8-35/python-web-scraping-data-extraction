"""Unit tests for the Selenium JavaScript Quotes scraper and HTML parsing."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException

from scraping_system.selenium.quotes_scraper import (
    _is_transient,
    _next_page,
    create_driver,
    parse_quotes,
    scrape_quotes,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSeleniumScraper(unittest.TestCase):
    def setUp(self):
        self.page1_html = (FIXTURES_DIR / "quotes_page.html").read_text(encoding="utf-8")
        self.page10_html = (FIXTURES_DIR / "quotes_last_page.html").read_text(encoding="utf-8")

    def test_parse_quotes_extracts_expected_fields(self):
        source_url = "https://quotes.toscrape.com/js/"
        records = parse_quotes(self.page1_html, source_url)

        self.assertEqual(len(records), 3)
        first = records[0]
        self.assertIn("The world as we have created it", first["quote"])
        self.assertEqual(first["author"], "Albert Einstein")
        self.assertIn("change", first["tags"])
        self.assertIn("deep-thoughts", first["tags"])
        self.assertEqual(first["source_url"], source_url)
        self.assertEqual(first["source"], "quotes.toscrape.com")

        second = records[1]
        self.assertIn("It is our choices, Harry", second["quote"])
        self.assertEqual(second["author"], "J.K. Rowling")
        self.assertEqual(second["tags"], ["abilities", "choices"])

    def test_parse_quotes_handles_empty_html(self):
        records = parse_quotes("<html><body></body></html>", "https://quotes.toscrape.com/js/")
        self.assertEqual(records, [])

    def test_next_page_detection_and_resolution(self):
        current_url = "https://quotes.toscrape.com/js/"
        next_url = _next_page(self.page1_html, current_url)
        self.assertEqual(next_url, "https://quotes.toscrape.com/js/page/2/")

    def test_next_page_returns_none_on_last_page(self):
        current_url = "https://quotes.toscrape.com/js/page/10/"
        next_url = _next_page(self.page10_html, current_url)
        self.assertIsNone(next_url)

    def test_next_page_rejects_unapproved_domain_or_path(self):
        malicious_html = '<li class="next"><a href="https://evil.com/phishing">Next</a></li>'
        with self.assertRaises(ValueError):
            _next_page(malicious_html, "https://quotes.toscrape.com/js/")

        wrong_path_html = (
            '<li class="next"><a href="https://quotes.toscrape.com/admin/">Next</a></li>'
        )
        with self.assertRaises(ValueError):
            _next_page(wrong_path_html, "https://quotes.toscrape.com/js/")

    def test_is_transient_classification(self):
        self.assertTrue(_is_transient(TimeoutException("Timed out waiting for element")))
        self.assertTrue(_is_transient(WebDriverException("net::ERR_CONNECTION_RESET")))
        self.assertTrue(_is_transient(ConnectionResetError("Connection reset by peer")))
        self.assertTrue(_is_transient(TimeoutError("Operation timed out")))

        self.assertFalse(_is_transient(NoSuchElementException("Element not found")))
        self.assertFalse(_is_transient(ValueError("Invalid argument")))
        self.assertFalse(_is_transient(TypeError("Type error")))

    @patch("scraping_system.selenium.quotes_scraper.webdriver.Chrome")
    def test_create_driver_local(self, mock_chrome):
        mock_config = MagicMock()
        mock_config.headless = True
        mock_config.browser_binary = "/custom/chrome"
        mock_config.selenium_url = None

        driver = create_driver(mock_config)
        mock_chrome.assert_called_once()
        self.assertEqual(driver, mock_chrome.return_value)

    @patch("scraping_system.selenium.quotes_scraper.webdriver.Remote")
    def test_create_driver_remote(self, mock_remote):
        mock_config = MagicMock()
        mock_config.headless = True
        mock_config.browser_binary = None
        mock_config.selenium_url = "http://localhost:4444/wd/hub"

        driver = create_driver(mock_config)
        mock_remote.assert_called_once()
        self.assertEqual(driver, mock_remote.return_value)

    @patch("scraping_system.selenium.quotes_scraper.create_driver")
    def test_scrape_quotes_guarantees_cleanup_on_success(self, mock_create):
        mock_driver = MagicMock()
        mock_driver.page_source = self.page10_html
        mock_create.return_value = mock_driver

        mock_config = MagicMock()
        mock_config.max_pages = 1
        mock_config.max_items = None
        mock_config.delay = 0
        mock_config.timeout = 5
        mock_config.retries = 0

        mock_pipeline = MagicMock()
        mock_pipeline.metrics.pages_processed = 0
        mock_pipeline.metrics.retries = 0
        mock_pipeline.records = []

        scrape_quotes(mock_config, mock_pipeline)

        self.assertEqual(mock_pipeline.metrics.pages_processed, 1)
        mock_pipeline.process.assert_called()
        mock_driver.quit.assert_called_once()

    @patch("scraping_system.selenium.quotes_scraper.create_driver")
    def test_scrape_quotes_guarantees_cleanup_on_failure(self, mock_create):
        mock_driver = MagicMock()
        mock_driver.get.side_effect = TimeoutException("Gateway timeout")
        mock_create.return_value = mock_driver

        mock_config = MagicMock()
        mock_config.max_pages = 2
        mock_config.max_items = None
        mock_config.delay = 0
        mock_config.timeout = 1
        mock_config.retries = 1

        mock_pipeline = MagicMock()
        mock_pipeline.metrics.pages_processed = 0
        mock_pipeline.metrics.retries = 0
        mock_pipeline.records = []

        with self.assertRaises(TimeoutException):
            scrape_quotes(mock_config, mock_pipeline)

        mock_driver.quit.assert_called_once()
        self.assertEqual(mock_pipeline.metrics.retries, 1)

    @patch("scraping_system.selenium.quotes_scraper.create_driver")
    def test_scrape_quotes_enforces_max_items(self, mock_create):
        mock_driver = MagicMock()
        mock_driver.page_source = self.page1_html
        mock_create.return_value = mock_driver

        mock_config = MagicMock()
        mock_config.max_pages = 5
        mock_config.max_items = 2
        mock_config.delay = 0
        mock_config.timeout = 5
        mock_config.retries = 0

        mock_pipeline = MagicMock()
        mock_pipeline.metrics.pages_processed = 0
        mock_pipeline.records = []

        def fake_process(raw, kind):
            mock_pipeline.records.append(raw)
            return raw

        mock_pipeline.process.side_effect = fake_process

        scrape_quotes(mock_config, mock_pipeline)

        self.assertEqual(len(mock_pipeline.records), 2)
        mock_driver.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
