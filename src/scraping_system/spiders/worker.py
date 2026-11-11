"""Isolated reactor worker; private JSON stdin/stdout protocol for the CLI."""

import json
import sys

from scrapy import signals
from scrapy.crawler import CrawlerProcess

from scraping_system.config import Settings
from scraping_system.models import RunMetrics
from scraping_system.pipelines import ProcessingPipeline
from scraping_system.spiders.books_spider import BooksSpider
from scraping_system.utils.logging import configure_logging


def main() -> None:
    request = json.load(sys.stdin)
    config = Settings(**request["config"])
    metrics = RunMetrics.model_validate(request["metrics"])
    pipeline = ProcessingPipeline(metrics)
    configure_logging(request.get("log_level", "INFO"))
    process = CrawlerProcess(
        {
            "LOG_ENABLED": False,
            "LOG_INSTALL_ROOT_HANDLER": False,
            "ROBOTSTXT_OBEY": True,
            "USER_AGENT": "ScrapingSystem/1.0 (+demo-site educational extraction)",
            "CONCURRENT_REQUESTS": 1,
            "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
            "DOWNLOAD_DELAY": config.delay,
            "DOWNLOAD_DELAY_JITTER": 0,
            "DOWNLOAD_TIMEOUT": config.timeout,
            "RETRY_TIMES": config.retries,
            "COOKIES_ENABLED": False,
            "TELNETCONSOLE_ENABLED": False,
            "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
            "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoDiskQueue",
            "ITEM_PIPELINES": {"scraping_system.spiders.books_spider.ScrapyProcessingAdapter": 100},
        },
    )
    configure_logging(request.get("log_level", "INFO"))
    crawler = process.create_crawler(BooksSpider)

    def spider_error(failure, response, spider):
        metrics.errors.append(f"Parser failure at {response.url}: {failure.type.__name__}")

    crawler.signals.connect(spider_error, signal=signals.spider_error, weak=False)
    deferred = process.crawl(crawler, config=config, pipeline=pipeline)

    def crawl_error(failure):
        metrics.errors.append(f"Crawler failed: {failure.type.__name__}")

    deferred.addErrback(crawl_error)
    process.start()
    stats = crawler.stats.get_stats() if crawler.stats else {}
    metrics.retries = stats.get("retry/count", 0)
    finish_reason = stats.get("finish_reason")
    if finish_reason not in {"finished", "item_limit"}:
        metrics.errors.append(f"Crawler stopped: {finish_reason or 'startup failure'}")
    if not metrics.pages_processed:
        metrics.errors.append("No catalogue pages were processed")
    result = {
        "metrics": metrics.model_dump(mode="json"),
        "records": [record.model_dump(mode="json") for record in pipeline.records],
        "rejected": pipeline.rejected,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
