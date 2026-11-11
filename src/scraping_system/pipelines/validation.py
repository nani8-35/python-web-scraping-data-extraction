"""One accountable processing path shared by Scrapy and Selenium."""

import json
import logging

from pydantic import ValidationError

from scraping_system.models import BookRecord, QuoteRecord, Record, RunMetrics
from scraping_system.pipelines.deduplication import Deduplicator
from scraping_system.pipelines.normalization import normalize_currency, parse_price, parse_rating

LOGGER = logging.getLogger(__name__)


class ProcessingPipeline:
    def __init__(self, metrics: RunMetrics) -> None:
        self.metrics = metrics
        self.records: list[Record] = []
        self.rejected: list[dict] = []
        self.deduplicator = Deduplicator()

    def process(self, raw: dict, kind: str) -> Record | None:
        if kind not in {"books", "quotes"}:
            raise ValueError(f"Unknown record kind: {kind}")
        self.metrics.extracted += 1
        try:
            values = dict(raw)
            if kind == "books":
                values["price"] = parse_price(values.get("price", ""))
                values["currency"] = normalize_currency(values.get("currency", "GBP"))
                values["rating"] = parse_rating(values.get("rating", ""))
                record = BookRecord.model_validate(values)
            else:
                record = QuoteRecord.model_validate(values)
        except (ValueError, ValidationError) as exc:
            self.metrics.invalid += 1
            self.rejected.append(
                {"record": json.loads(json.dumps(raw, default=str)), "reason": str(exc)}
            )
            LOGGER.warning(
                "record_rejected", extra={"run_id": self.metrics.run_id, "reason": str(exc)}
            )
            return None
        if self.deduplicator.is_duplicate(record.record_id):
            self.metrics.duplicates += 1
            return None
        self.records.append(record)
        self.metrics.accepted += 1
        return record
