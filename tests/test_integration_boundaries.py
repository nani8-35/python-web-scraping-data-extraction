"""Offline regression checks for production boundaries and failure semantics."""

import csv
import json
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request
from typer.testing import CliRunner

from scraping_system import cli
from scraping_system.config import Settings
from scraping_system.exporters import export_records
from scraping_system.models import BookRecord, QuoteRecord, RunMetrics
from scraping_system.pipelines import ProcessingPipeline
from scraping_system.pipelines.normalization import normalize_url, parse_price
from scraping_system.spiders.books_spider import BooksSpider
from scraping_system.utils.files import atomic_text

FIXTURES = Path(__file__).parent / "fixtures"


def response(name, url):
    return HtmlResponse(
        url, body=(FIXTURES / name).read_bytes(), encoding="utf-8", request=Request(url)
    )


def test_actual_spider_detail_and_pipeline():
    spider = BooksSpider(config=Settings(_env_file=None))
    page = response("book_detail_page.html", "https://books.toscrape.com/catalogue/book/index.html")
    raw = next(spider.parse_book(page))
    record = spider.pipeline.process(raw, "books")
    assert isinstance(record, BookRecord)
    assert record.title == "A Light in the Attic"
    assert str(record.price) == "51.77"
    assert record.rating == 3
    assert record.category == "Poetry"


def test_actual_spider_pagination_and_page_limit():
    page = response("books_list_page.html", "https://books.toscrape.com/")
    spider = BooksSpider(config=Settings(max_pages=2, _env_file=None))
    requests = list(spider.parse(page))
    assert len(requests) == 3
    assert requests[-1].url == "https://books.toscrape.com/catalogue/page-2.html"
    assert all(request.url.startswith("https://books.toscrape.com/") for request in requests)
    bounded = BooksSpider(config=Settings(max_pages=1, max_items=1, _env_file=None))
    assert len(list(bounded.parse(page))) == 1


@pytest.mark.parametrize("value", ["NaN", "Infinity", "12.345", "1,23.45", "9" * 60])
def test_invalid_prices_are_rejected_without_crashing_pipeline(value):
    pipeline = ProcessingPipeline(RunMetrics(source="books"))
    assert pipeline.process({"price": value}, "books") is None
    assert pipeline.metrics.invalid == 1
    assert pipeline.metrics.extracted == 1


def test_price_exactness_and_url_canonicalization():
    assert str(parse_price("£1,234.50")) == "1234.50"
    assert normalize_url("HTTPS://BOOKS.TOSCRAPE.COM:443/a?b=1#fragment") == (
        "https://books.toscrape.com/a?b=1"
    )


def test_quote_dedup_across_pages_after_normalization():
    pipeline = ProcessingPipeline(RunMetrics(source="quotes"))
    raw = {
        "quote": " A  quote ",
        "author": " An Author ",
        "tags": ["tag", " tag ", ""],
        "source_url": "https://quotes.toscrape.com/js/",
    }
    record = pipeline.process(raw, "quotes")
    assert record.tags == ["tag"]
    pipeline.process(
        {**raw, "quote": "A quote", "source_url": "https://quotes.toscrape.com/js/page/2/"},
        "quotes",
    )
    assert pipeline.metrics.extracted == 2
    assert pipeline.metrics.accepted == 1
    assert pipeline.metrics.duplicates == 1


def test_csv_empty_headers_and_formula_guard(tmp_path):
    destination = tmp_path / "empty.csv"
    export_records([], "csv", destination, RunMetrics(source="quotes"))
    assert destination.read_text().startswith("quote,author,tags,source_url,source,scraped_at")
    record = QuoteRecord(quote="=1+2", author="A", source_url="https://quotes.toscrape.com/js/")
    export_records([record], "csv", destination, RunMetrics(source="quotes"))
    with destination.open(newline="") as stream:
        assert next(csv.DictReader(stream))["quote"] == "'=1+2"


def test_atomic_write_preserves_previous_artifact_on_failure(tmp_path):
    destination = tmp_path / "records.json"
    destination.write_text("original")
    with pytest.raises(RuntimeError), atomic_text(destination) as stream:
        stream.write("partial replacement")
        raise RuntimeError("Simulated disk/export failure")
    assert destination.read_text() == "original"
    assert list(tmp_path.iterdir()) == [destination]


def test_settings_environment_precedence(monkeypatch):
    monkeypatch.setenv("SCRAPING_MAX_PAGES", "7")
    assert Settings(_env_file=None).max_pages == 7
    assert Settings(max_pages=3, _env_file=None).max_pages == 3
    monkeypatch.setenv("SCRAPING_MAX_PAGES", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_cli_failure_retains_partial_data_and_failed_report(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fail(config, pipeline, log_level):
        pipeline.metrics.errors.append("HTTP request failed after retries")
        pipeline.metrics.pages_processed = 1

    monkeypatch.setattr(cli, "scrape_books", fail)
    result = CliRunner().invoke(cli.app, ["books", "--format", "json"])
    assert result.exit_code == 1
    metrics = json.loads((tmp_path / "artifacts/books_run.json").read_text())
    assert metrics["status"] == "failed"
    assert "HTTP request failed" in (tmp_path / "artifacts/report.html").read_text()
    assert json.loads((tmp_path / "artifacts/books.json").read_text()) == []


def test_cli_all_separates_records_and_applies_limits(monkeypatch, tmp_path):
    from scraping_system.selenium import quotes_scraper

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "scrape_books", lambda *args: None)
    monkeypatch.setattr(quotes_scraper, "scrape_quotes", lambda *args: None)
    result = CliRunner().invoke(cli.app, ["all", "--output", "out", "--max-items", "2"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out/books.json").is_file()
    assert (tmp_path / "out/quotes.json").is_file()


def test_cli_rejects_invalid_limits_before_starting_browser():
    assert CliRunner().invoke(cli.app, ["quotes", "--max-pages", "0"]).exit_code == 2
