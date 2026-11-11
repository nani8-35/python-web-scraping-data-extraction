"""Single exporter dispatch boundary for CLI and integrations."""

from pathlib import Path

from scraping_system.exporters.csv_exporter import export_csv
from scraping_system.exporters.json_exporter import export_json
from scraping_system.models import BookRecord, Record, RunMetrics


def export_records(
    records: list[Record],
    format: str,
    destination: Path,
    metrics: RunMetrics,
    database_url: str | None = None,
) -> str:
    if format == "json":
        return str(export_json(records, destination))
    if format == "csv":
        kind = (
            "books"
            if (
                (records and isinstance(records[0], BookRecord))
                or (not records and "books" in metrics.source)
            )
            else "quotes"
        )
        return str(export_csv(records, destination, kind))
    if format == "postgres":
        if not database_url:
            raise ValueError("Set SCRAPING_DATABASE_URL for PostgreSQL export")
        from scraping_system.exporters.postgres_exporter import export_postgres

        return export_postgres(records, database_url, metrics)
    raise ValueError(f"Unsupported export format: {format}")
