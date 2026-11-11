"""Browser-backed extraction of the public JavaScript Quotes demo."""

from scraping_system.selenium.quotes_scraper import parse_quotes, scrape_quotes

__all__ = ["parse_quotes", "scrape_quotes"]
