"""Validated records and transportable run metrics."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scraping_system.pipelines.normalization import normalize_url, normalize_whitespace


def utc_now() -> datetime:
    return datetime.now(UTC)


def stable_id(*values: str) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()


class BaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    source: str
    scraped_at: datetime = Field(default_factory=utc_now)

    @field_validator("source")
    @classmethod
    def source_valid(cls, value: str) -> str:
        value = normalize_whitespace(value).lower()
        if not value:
            raise ValueError("Source cannot be empty")
        return value

    @field_validator("scraped_at")
    @classmethod
    def timestamp_valid(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scraped_at must include a timezone")
        return value.astimezone(UTC)


class BookRecord(BaseRecord):
    title: str
    price: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
    currency: Literal["GBP", "USD", "EUR"] = "GBP"
    availability: str
    rating: Annotated[int, Field(ge=1, le=5, strict=True)]
    category: str
    product_url: str
    source: str = "books.toscrape.com"

    @field_validator("title", "availability", "category")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = normalize_whitespace(value)
        if not value:
            raise ValueError("Text cannot be empty")
        return value

    @field_validator("product_url")
    @classmethod
    def url_valid(cls, value: str) -> str:
        return normalize_url(value)

    @property
    def record_id(self) -> str:
        return stable_id(self.source, self.product_url)


class QuoteRecord(BaseRecord):
    quote: str
    author: str
    tags: list[str] = Field(default_factory=list)
    source_url: str
    source: str = "quotes.toscrape.com"

    @field_validator("quote", "author")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        value = normalize_whitespace(value)
        if not value:
            raise ValueError("Text cannot be empty")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(tag for v in value if (tag := normalize_whitespace(v))))

    @field_validator("source_url")
    @classmethod
    def url_valid(cls, value: str) -> str:
        return normalize_url(value)

    @property
    def record_id(self) -> str:
        return stable_id(self.quote, self.author)


Record = BookRecord | QuoteRecord


class RunMetrics(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    pages_processed: int = Field(default=0, ge=0)
    extracted: int = Field(default=0, ge=0)
    accepted: int = Field(default=0, ge=0)
    invalid: int = Field(default=0, ge=0)
    duplicates: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    output_format: str = "json"
    output_path: str = ""
    status: Literal["running", "success", "failed", "interrupted"] = "running"
    errors: list[str] = Field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, ((self.finished_at or utc_now()) - self.started_at).total_seconds())

    def finish(self, status: str) -> None:
        self.status = status
        self.finished_at = utc_now()
