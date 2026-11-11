"""Render Quotes to Scrape with Selenium, then parse its DOM with BeautifulSoup.

Browser creation is deliberately deferred until ``scrape_quotes`` is called.
Selenium Manager discovers a local Chrome driver automatically; a remote
Selenium endpoint and an explicit Chrome binary are also supported.
"""

from __future__ import annotations

import logging
from threading import Event
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

if TYPE_CHECKING:
    from scraping_system.config import Settings
    from scraping_system.pipelines import ProcessingPipeline

LOGGER = logging.getLogger(__name__)
START_URL = "https://quotes.toscrape.com/js/"


def parse_quotes(html: str, source_url: str) -> list[dict]:
    """Extract raw records, including malformed ones for downstream validation.

    Text normalization and rejection accounting belong to the shared pipeline.
    Keeping this function browser-independent permits realistic fixture tests.
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for node in soup.select("div.quote"):
        quote = node.select_one(".text")
        author = node.select_one(".author")
        tags = [tag.get_text() for tag in node.select(".tags .tag")]
        if not tags:
            tags = [tag.get_text() for tag in node.select("a.tag")]
        records.append(
            {
                "quote": quote.get_text() if quote else "",
                "author": author.get_text() if author else "",
                "tags": tags,
                "source_url": source_url,
                "source": "quotes.toscrape.com",
            }
        )
    return records


def create_driver(config: Settings) -> webdriver.Remote:
    """Create a local Chrome or explicitly configured remote browser."""
    options = webdriver.ChromeOptions()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-dev-shm-usage")
    if config.browser_binary:
        options.binary_location = config.browser_binary
    if config.selenium_url:
        return webdriver.Remote(command_executor=config.selenium_url, options=options)
    return webdriver.Chrome(options=options)


def _next_page(html: str, current_url: str) -> str | None:
    link = BeautifulSoup(html, "html.parser").select_one("li.next a[href]")
    if link is None:
        return None
    next_url = urljoin(current_url, str(link["href"]))
    parts = urlsplit(next_url)
    netloc_host = parts.netloc.split(":")[0]
    if (
        parts.scheme not in ("http", "https")
        or netloc_host != "quotes.toscrape.com"
        or not parts.path.startswith("/js/")
    ):
        raise ValueError(f"Refusing pagination outside the approved JavaScript demo: {next_url}")
    return next_url


def _is_transient(exc: Exception) -> bool:
    """Identify transient navigation or network faults suitable for retry.

    Invalid arguments, selector bugs, and programming errors are deliberately excluded.
    """
    if isinstance(exc, TimeoutException):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    exc_str = str(exc)
    return any(
        marker in exc_str
        for marker in (
            "net::ERR_CONNECTION_RESET",
            "net::ERR_CONNECTION_CLOSED",
            "net::ERR_CONNECTION_TIMED_OUT",
            "net::ERR_TIMED_OUT",
            "net::ERR_NETWORK_CHANGED",
            "net::ERR_NAME_NOT_RESOLVED",
            "Connection refused",
            "Connection reset",
        )
    )


def _load_page(
    driver: webdriver.Remote, url: str, config: Settings, pipeline: ProcessingPipeline
) -> str:
    for attempt in range(config.retries + 1):
        try:
            driver.get(url)
            WebDriverWait(driver, config.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.quote"))
            )
            return driver.page_source
        except Exception as exc:
            if (
                not isinstance(exc, (WebDriverException, ConnectionError, OSError))
                or not _is_transient(exc)
                or attempt >= config.retries
            ):
                raise
            pipeline.metrics.retries += 1
            LOGGER.warning(
                "quotes_page_retry",
                extra={
                    "run_id": pipeline.metrics.run_id,
                    "source": "quotes.toscrape.com",
                    "url": url,
                    "attempt": attempt + 1,
                    "error": str(exc),
                },
            )
            # Bounded retry backoff, not a substitute for DOM waits.
            Event().wait(min(2**attempt, 8))
    raise RuntimeError("Unreachable retry state")


def scrape_quotes(config: Settings, pipeline: ProcessingPipeline) -> None:
    """Scrape bounded pages; always close every successfully created browser.

    ``max_items`` limits accepted unique records. Operational failures propagate
    to the CLI so it can persist a failed run and any already collected records.
    """
    driver = create_driver(config)
    try:
        driver.set_page_load_timeout(config.timeout)
        url: str | None = START_URL
        visited: set[str] = set()
        while url is not None and pipeline.metrics.pages_processed < config.max_pages:
            if config.max_items is not None and len(pipeline.records) >= config.max_items:
                break
            if url in visited:
                raise ValueError(f"Pagination cycle detected at {url}")
            visited.add(url)
            if pipeline.metrics.pages_processed and config.delay:
                # Explicit crawl politeness between requests, not a render wait.
                Event().wait(config.delay)
            html = _load_page(driver, url, config, pipeline)
            pipeline.metrics.pages_processed += 1
            for raw in parse_quotes(html, url):
                pipeline.process(raw, "quotes")
                if config.max_items is not None and len(pipeline.records) >= config.max_items:
                    break
            LOGGER.info(
                "quotes_page_processed",
                extra={
                    "run_id": pipeline.metrics.run_id,
                    "source": "quotes.toscrape.com",
                    "url": url,
                    "pages_processed": pipeline.metrics.pages_processed,
                    "extracted": pipeline.metrics.extracted,
                    "accepted": pipeline.metrics.accepted,
                    "invalid": pipeline.metrics.invalid,
                    "duplicates": pipeline.metrics.duplicates,
                },
            )
            if config.max_items is not None and len(pipeline.records) >= config.max_items:
                break
            if pipeline.metrics.pages_processed >= config.max_pages:
                break
            url = _next_page(html, url)
    finally:
        try:
            driver.quit()
        except Exception:
            # A vanished remote browser cannot be closed; never mask the scrape
            # exception with an unrelated cleanup exception.
            LOGGER.warning(
                "quotes_browser_cleanup_failed",
                extra={"run_id": pipeline.metrics.run_id},
                exc_info=True,
            )
