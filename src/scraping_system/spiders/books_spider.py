"""Bounded catalogue pagination followed by product-detail extraction."""

import logging

import scrapy
from scrapy.exceptions import CloseSpider
from scrapy.http import Response

from scraping_system.config import Settings
from scraping_system.models import RunMetrics
from scraping_system.pipelines import ProcessingPipeline

LOGGER = logging.getLogger(__name__)


class BooksSpider(scrapy.Spider):
    name = "books"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    def __init__(
        self, config: Settings | None = None, pipeline: ProcessingPipeline | None = None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.config = config or Settings()
        self.pipeline = pipeline or ProcessingPipeline(RunMetrics(source="books"))

    async def start(self):
        yield scrapy.Request(self.start_urls[0], callback=self.parse, errback=self.request_failed)

    def parse(self, response: Response):
        self.pipeline.metrics.pages_processed += 1
        links = response.css("article.product_pod h3 a::attr(href)").getall()
        if not links:
            self.pipeline.metrics.errors.append(f"No product links found: {response.url}")
            raise CloseSpider("empty_catalogue")
        remaining = self.config.max_items
        if remaining is not None:
            remaining -= len(self.pipeline.records)
            links = links[: max(0, remaining)]
        LOGGER.info(
            "books_page_processed",
            extra={
                "run_id": self.pipeline.metrics.run_id,
                "url": response.url,
                "pages_processed": self.pipeline.metrics.pages_processed,
            },
        )
        for link in links:
            yield response.follow(
                link, callback=self.parse_book, errback=self.request_failed, priority=10
            )
        next_url = response.css("li.next a::attr(href)").get()
        if next_url and self.pipeline.metrics.pages_processed < self.config.max_pages:
            yield response.follow(
                next_url, callback=self.parse, errback=self.request_failed, priority=-10
            )

    def parse_book(self, response: Response):
        if (
            self.config.max_items is not None
            and len(self.pipeline.records) >= self.config.max_items
        ):
            raise CloseSpider("item_limit")
        rating_class = response.css(".product_main .star-rating::attr(class)").get("")
        yield {
            "title": response.css(".product_main h1::text").get(""),
            "price": response.css(".product_main .price_color::text").get(""),
            "currency": "GBP",
            "availability": " ".join(response.css(".product_main .availability::text").getall()),
            "rating": rating_class.replace("star-rating", "").strip(),
            "category": response.css("ul.breadcrumb li:nth-last-child(2) a::text").get(""),
            "product_url": response.url,
            "source": "books.toscrape.com",
        }

    def request_failed(self, failure) -> None:
        self.pipeline.metrics.errors.append(
            f"Request failed after retries: {failure.request.url} ({failure.type.__name__})"
        )


class ScrapyProcessingAdapter:
    @classmethod
    def from_crawler(cls, crawler):
        instance = cls()
        instance.crawler = crawler
        return instance

    async def process_item(self, item):
        spider = self.crawler.spider
        spider.pipeline.process(dict(item), "books")
        if (
            spider.config.max_items is not None
            and len(spider.pipeline.records) >= spider.config.max_items
        ):
            # Schedule closure separately: waiting here would deadlock item draining.
            import asyncio

            asyncio.create_task(self.crawler.engine.close_spider_async(reason="item_limit"))
        return item
