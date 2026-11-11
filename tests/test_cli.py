"""Unit tests for the Typer CLI commands, error handling, and reporting."""

import logging
import sys
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from scraping_system.cli import app


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def tearDown(self):
        root = logging.getLogger()
        root.handlers = [logging.StreamHandler(sys.stderr)]

    def test_cli_help(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("books", result.output)
        self.assertIn("quotes", result.output)
        self.assertIn("all", result.output)

    def test_cli_invalid_source(self):
        result = self.runner.invoke(app, ["invalid_source"])
        self.assertNotEqual(result.exit_code, 0)

    def test_cli_invalid_format(self):
        result = self.runner.invoke(app, ["books", "--format", "parquet"])
        self.assertNotEqual(result.exit_code, 0)

    def test_cli_postgres_missing_database_url_fails(self):
        with patch.dict("os.environ", {}, clear=True):
            result = self.runner.invoke(
                app,
                ["books", "--format", "postgres", "--max-pages", "1", "--no-generate-report"],
            )
            self.assertNotEqual(result.exit_code, 0)

    @patch("scraping_system.reporting.html_report.generate_report")
    @patch("scraping_system.selenium.quotes_scraper.scrape_quotes")
    @patch("scraping_system.cli.export_records")
    def test_cli_quotes_success_generates_report(self, mock_export, mock_scrape, mock_report):
        mock_export.return_value = "artifacts/quotes.json"

        def fake_scrape(config, pipeline):
            pipeline.metrics.pages_processed = 1
            pipeline.metrics.extracted = 10
            pipeline.metrics.accepted = 10

        mock_scrape.side_effect = fake_scrape

        result = self.runner.invoke(
            app,
            ["quotes", "--max-pages", "1", "--format", "json", "--generate-report"],
        )
        self.assertEqual(result.exit_code, 0)
        mock_scrape.assert_called_once()
        mock_report.assert_called_once()

    @patch("scraping_system.reporting.html_report.generate_report")
    @patch("scraping_system.selenium.quotes_scraper.scrape_quotes")
    def test_cli_quotes_failure_marks_failed_and_generates_report(self, mock_scrape, mock_report):
        mock_scrape.side_effect = RuntimeError("Selenium driver crashed")

        result = self.runner.invoke(
            app,
            ["quotes", "--max-pages", "1", "--format", "json", "--generate-report"],
        )
        self.assertNotEqual(result.exit_code, 0)
        mock_report.assert_called_once()
        args, _ = mock_report.call_args
        runs = args[0]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "failed")


if __name__ == "__main__":
    unittest.main()
