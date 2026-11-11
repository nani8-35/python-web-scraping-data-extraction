"""Shared normalize → validate → deduplicate ingestion boundary."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scraping_system.pipelines.validation import ProcessingPipeline as ProcessingPipeline


def __getattr__(name: str):
    # Keep normalization usable by models without an import cycle.
    if name == "ProcessingPipeline":
        from scraping_system.pipelines.validation import ProcessingPipeline

        return ProcessingPipeline
    raise AttributeError(name)
