"""Transactional, idempotent persistence with bounded transient retries."""

import logging
from threading import Event

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError

from scraping_system.database.connection import create_database_engine
from scraping_system.database.models import books, metadata, quotes, scrape_runs
from scraping_system.models import BookRecord, Record, RunMetrics

LOGGER = logging.getLogger(__name__)


def export_postgres(records: list[Record], database_url: str, metrics: RunMetrics) -> str:
    engine = create_database_engine(database_url)
    try:
        for attempt in range(3):
            try:
                with engine.begin() as connection:
                    metadata.create_all(connection)
                    for record in records:
                        table = books if isinstance(record, BookRecord) else quotes
                        values = record.model_dump()
                        values["record_id"] = record.record_id
                        statement = insert(table).values(**values)
                        connection.execute(
                            statement.on_conflict_do_update(
                                index_elements=[table.c.record_id],
                                set_={
                                    key: statement.excluded[key]
                                    for key in values
                                    if key != "record_id"
                                },
                            )
                        )
                    # Mark the snapshot final inside the same transaction as its records.
                    snapshot = metrics.model_copy(deep=True)
                    snapshot.output_path = "postgresql:books/quotes/scrape_runs"
                    snapshot.finish("failed" if snapshot.errors else "success")
                    values = snapshot.model_dump()
                    values["elapsed_seconds"] = snapshot.elapsed_seconds
                    statement = insert(scrape_runs).values(**values)
                    connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[scrape_runs.c.run_id],
                            set_={
                                key: statement.excluded[key] for key in values if key != "run_id"
                            },
                        )
                    )
                return "postgresql:books/quotes/scrape_runs"
            except OperationalError as exc:
                state = getattr(exc.orig, "sqlstate", None)
                transient = (
                    state is None or state.startswith("08") or state in {"40001", "40P01", "57P03"}
                )
                if not transient or attempt == 2:
                    raise
                metrics.retries += 1
                LOGGER.warning(
                    "database_retry", extra={"run_id": metrics.run_id, "attempt": attempt + 1}
                )
                Event().wait(2**attempt)
    finally:
        engine.dispose()
    raise RuntimeError("Unreachable database retry state")
