"""CLI workflow for bounded scraping, export, and durable run summaries."""

import json
import logging
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from scraping_system.config import Settings
from scraping_system.exporters import export_records
from scraping_system.models import BookRecord, Record, RunMetrics
from scraping_system.pipelines import ProcessingPipeline
from scraping_system.utils.files import atomic_text
from scraping_system.utils.logging import configure_logging

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
LOGGER = logging.getLogger(__name__)


class Source(StrEnum):
    books = "books"
    quotes = "quotes"
    all = "all"


class ExportFormat(StrEnum):
    csv = "csv"
    json = "json"
    postgres = "postgres"


def scrape_books(config: Settings, pipeline: ProcessingPipeline, log_level: str) -> None:
    request = {
        "config": config.model_dump(exclude={"database_url"}),
        "metrics": pipeline.metrics.model_dump(mode="json"),
        "log_level": log_level,
    }
    result = subprocess.run(
        [sys.executable, "-m", "scraping_system.spiders.worker"],
        input=json.dumps(request),
        text=True,
        stdout=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Scrapy worker exited with code {result.returncode}")
    payload = json.loads(result.stdout)
    pipeline.metrics = RunMetrics.model_validate(payload["metrics"])
    pipeline.records = [BookRecord.model_validate(record) for record in payload["records"]]
    pipeline.rejected = payload["rejected"]


def save_metrics(pipeline: ProcessingPipeline, kind: str) -> None:
    metrics = pipeline.metrics
    with atomic_text(Path("artifacts") / f"{kind}_run.json") as stream:
        json.dump(
            {**metrics.model_dump(mode="json"), "elapsed_seconds": metrics.elapsed_seconds},
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    # Always replace this file so an earlier failed run cannot leave stale rejections.
    with atomic_text(Path("artifacts") / f"{kind}_rejected_records.json") as stream:
        json.dump(pipeline.rejected, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run_source(
    kind: str,
    config: Settings,
    format: str,
    destination: Path,
    log_level: str,
) -> ProcessingPipeline:
    pipeline = ProcessingPipeline(RunMetrics(source=kind, output_format=format))
    LOGGER.info("scraper_started", extra={"run_id": pipeline.metrics.run_id, "source": kind})
    interrupted = False
    try:
        if kind == "books":
            scrape_books(config, pipeline, log_level)
        else:
            from scraping_system.selenium.quotes_scraper import scrape_quotes

            scrape_quotes(config, pipeline)
    except KeyboardInterrupt:
        interrupted = True
        pipeline.metrics.errors.append("Scraping interrupted by the operator")
    except Exception as exc:
        # Exception messages from drivers/DB libraries may contain connection credentials.
        pipeline.metrics.errors.append(f"Scraping failed ({type(exc).__name__})")
        LOGGER.error(
            "scraping_failed",
            extra={"run_id": pipeline.metrics.run_id, "reason": type(exc).__name__},
        )
    pipeline.records.sort(key=lambda record: record.record_id)
    try:
        pipeline.metrics.output_path = export_records(
            pipeline.records, format, destination, pipeline.metrics, config.database_url
        )
        LOGGER.info(
            "export_finished",
            extra={"run_id": pipeline.metrics.run_id, "destination": pipeline.metrics.output_path},
        )
    except Exception as exc:
        pipeline.metrics.errors.append(f"Export failed ({type(exc).__name__})")
        LOGGER.error(
            "export_failed", extra={"run_id": pipeline.metrics.run_id, "reason": type(exc).__name__}
        )
    pipeline.metrics.finish(
        "interrupted" if interrupted else "failed" if pipeline.metrics.errors else "success"
    )
    save_metrics(pipeline, kind)
    LOGGER.info(
        "scraper_finished",
        extra={
            **pipeline.metrics.model_dump(),
            "elapsed_seconds": pipeline.metrics.elapsed_seconds,
        },
    )
    return pipeline


@app.command()
def run(
    source: Annotated[Source, typer.Argument(help="Demo source: books, quotes, or all.")],
    format: Annotated[
        ExportFormat, typer.Option("--format", help="Export destination format.")
    ] = ExportFormat.json,
    output: Annotated[
        Path | None, typer.Option(help="File path; directory when source is all.")
    ] = None,
    max_pages: Annotated[
        int | None, typer.Option(min=1, help="Maximum catalogue/quote pages.")
    ] = None,
    max_items: Annotated[
        int | None, typer.Option(min=1, help="Maximum accepted records per source.")
    ] = None,
    headless: Annotated[bool | None, typer.Option("--headless/--no-headless")] = None,
    log_level: Annotated[str, typer.Option(help="DEBUG, INFO, WARNING, or ERROR.")] = "INFO",
    generate_report: Annotated[bool, typer.Option("--generate-report/--no-generate-report")] = True,
    delay: Annotated[
        float | None, typer.Option(min=0, help="Polite delay between requests.")
    ] = None,
) -> None:
    """Extract public demo-site data; emit metrics, rejections, and an HTML report."""
    if log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise typer.BadParameter("Choose DEBUG, INFO, WARNING, or ERROR", param_hint="--log-level")
    configure_logging(log_level)
    overrides = {
        "max_pages": max_pages,
        "max_items": max_items,
        "headless": headless,
        "delay": delay,
    }
    try:
        config = Settings(**{key: value for key, value in overrides.items() if value is not None})
    except ValidationError as exc:
        # Field names are actionable without leaking environment values.
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        raise typer.BadParameter(f"Invalid settings: {fields}") from None
    if format == ExportFormat.postgres and not config.database_url:
        raise typer.BadParameter("Set SCRAPING_DATABASE_URL before exporting to PostgreSQL")
    kinds = ["books", "quotes"] if source == Source.all else [source.value]
    if source == Source.all and output is not None and output.exists() and not output.is_dir():
        raise typer.BadParameter("--output must be a directory for all")
    runs: list[RunMetrics] = []
    records: list[Record] = []
    for kind in kinds:
        destination = (
            (output or Path("artifacts")) / f"{kind}.{format.value}"
            if source == Source.all
            else output or Path("artifacts") / f"{kind}.{format.value}"
        )
        try:
            pipeline = run_source(kind, config, format.value, destination, log_level)
        except OSError as exc:
            typer.echo(f"Could not write run artifacts ({type(exc).__name__}).", err=True)
            raise typer.Exit(1) from None
        runs.append(pipeline.metrics)
        records.extend(pipeline.records)
        typer.echo(
            f"{kind}: {pipeline.metrics.status}; {pipeline.metrics.accepted} accepted, "
            f"{pipeline.metrics.invalid} invalid, {pipeline.metrics.duplicates} duplicates"
        )
        if pipeline.metrics.status == "interrupted":
            break
    if generate_report:
        try:
            from scraping_system.reporting.html_report import generate_report as render_report

            render_report(runs, records, Path("artifacts/report.html"))
            typer.echo("Report: artifacts/report.html")
        except Exception as exc:
            typer.echo(f"Report generation failed ({type(exc).__name__}).", err=True)
            raise typer.Exit(1) from None
    if any(run.status == "interrupted" for run in runs):
        raise typer.Exit(130)
    if any(run.status != "success" for run in runs):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
