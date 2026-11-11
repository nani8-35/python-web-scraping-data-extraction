"""JSON-line logging without credentials or noisy dependency diagnostics."""

import json
import logging
from datetime import UTC, datetime

EXTRA_FIELDS = (
    "run_id",
    "source",
    "url",
    "pages_processed",
    "extracted",
    "accepted",
    "invalid",
    "duplicates",
    "retries",
    "destination",
    "elapsed_seconds",
    "status",
    "attempt",
    "reason",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(
            {name: getattr(record, name) for name in EXTRA_FIELDS if hasattr(record, name)}
        )
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level.upper())
    if level.upper() != "DEBUG":
        handler.addFilter(
            lambda record: (
                not record.name.startswith(("scrapy.", "selenium.", "urllib3."))
                or record.levelno >= logging.WARNING
            )
        )
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    for name in ("scrapy", "selenium", "urllib3", "twisted"):
        logging.getLogger(name).setLevel(logging.WARNING)
