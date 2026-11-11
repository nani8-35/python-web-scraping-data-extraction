"""Portable JSON arrays with exact decimal strings and ISO timestamps."""

import json
from pathlib import Path

from scraping_system.models import Record
from scraping_system.utils.files import atomic_text


def export_json(records: list[Record], destination: Path) -> Path:
    with atomic_text(destination) as stream:
        json.dump(
            [r.model_dump(mode="json") for r in records], stream, ensure_ascii=False, indent=2
        )
        stream.write("\n")
    return Path(destination)
