"""Explicit PostgreSQL schema; record identities support repeatable upserts."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
)

metadata = MetaData()
books = Table(
    "books",
    metadata,
    Column("record_id", String(64), primary_key=True),
    Column("title", String, nullable=False),
    Column("price", Numeric(12, 2), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("availability", String, nullable=False),
    Column("rating", Integer, nullable=False),
    Column("category", String, nullable=False, index=True),
    Column("product_url", String, nullable=False),
    Column("source", String, nullable=False, index=True),
    Column("scraped_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("price >= 0"),
    CheckConstraint("rating BETWEEN 1 AND 5"),
)
quotes = Table(
    "quotes",
    metadata,
    Column("record_id", String(64), primary_key=True),
    Column("quote", String, nullable=False),
    Column("author", String, nullable=False, index=True),
    Column("tags", JSON, nullable=False),
    Column("source_url", String, nullable=False),
    Column("source", String, nullable=False, index=True),
    Column("scraped_at", DateTime(timezone=True), nullable=False),
)
scrape_runs = Table(
    "scrape_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("source", String, nullable=False, index=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("pages_processed", Integer, nullable=False),
    Column("extracted", Integer, nullable=False),
    Column("accepted", Integer, nullable=False),
    Column("invalid", Integer, nullable=False),
    Column("duplicates", Integer, nullable=False),
    Column("retries", Integer, nullable=False),
    Column("output_format", String, nullable=False),
    Column("output_path", String, nullable=False),
    Column("status", String, nullable=False),
    Column("errors", JSON, nullable=False),
    Column("elapsed_seconds", Float, nullable=False),
)
