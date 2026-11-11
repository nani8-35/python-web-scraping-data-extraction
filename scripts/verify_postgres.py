"""Opt-in integration check against a configured PostgreSQL database.

Uses real sample records, writes them twice, and verifies stable row counts.
It creates the project tables if absent and never drops or clears tables.
"""

import json
from pathlib import Path

from sqlalchemy import func, select

from scraping_system.config import Settings
from scraping_system.database.connection import create_database_engine
from scraping_system.database.models import books, quotes, scrape_runs
from scraping_system.exporters import export_records
from scraping_system.models import BookRecord, QuoteRecord, RunMetrics
from scraping_system.utils.files import atomic_text


def main() -> None:
    config = Settings()
    if not config.database_url:
        raise SystemExit("Set SCRAPING_DATABASE_URL to an isolated verification database")
    records_by_kind = {}
    for kind, model in (("books", BookRecord), ("quotes", QuoteRecord)):
        samples = json.loads(Path(f"sample_output/{kind}_sample.json").read_text(encoding="utf-8"))
        records_by_kind[kind] = [model.model_validate(raw) for raw in samples]
    engine = create_database_engine(config.database_url)
    metrics_by_kind = {
        kind: RunMetrics(
            source=kind, output_format="postgres", extracted=len(records), accepted=len(records)
        )
        for kind, records in records_by_kind.items()
    }
    snapshots = []
    try:
        for _ in range(2):
            for kind, records in records_by_kind.items():
                export_records(
                    records, "postgres", Path("unused"), metrics_by_kind[kind], config.database_url
                )
            with engine.connect() as connection:
                counts = {
                    kind: connection.scalar(
                        select(func.count())
                        .select_from(table)
                        .where(table.c.record_id.in_([r.record_id for r in records_by_kind[kind]]))
                    )
                    for kind, table in (("books", books), ("quotes", quotes))
                }
                counts["runs"] = connection.scalar(
                    select(func.count())
                    .select_from(scrape_runs)
                    .where(scrape_runs.c.run_id.in_([m.run_id for m in metrics_by_kind.values()]))
                )
                snapshots.append(counts)
        assert snapshots[0] == snapshots[1], "Upserts created duplicate records/runs"
        assert snapshots[-1] == {
            "books": len(records_by_kind["books"]),
            "quotes": len(records_by_kind["quotes"]),
            "runs": 2,
        }
        with engine.connect() as connection:
            book = records_by_kind["books"][0]
            stored_price = connection.scalar(
                select(books.c.price).where(books.c.record_id == book.record_id)
            )
            assert stored_price == book.price, "Decimal price roundtrip failed"
            statuses = connection.scalars(
                select(scrape_runs.c.status).where(
                    scrape_runs.c.run_id.in_([m.run_id for m in metrics_by_kind.values()])
                )
            ).all()
            assert statuses == ["success", "success"]
        result = {
            "status": "passed",
            "checks": [
                "schema creation",
                "book/quote persistence",
                "decimal roundtrip",
                "idempotent record and run upserts",
                "final run status",
            ],
            "counts": snapshots[-1],
        }
        with atomic_text(Path("artifacts/postgres_verification.json")) as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
