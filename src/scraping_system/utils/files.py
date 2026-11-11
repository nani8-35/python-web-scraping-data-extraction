"""Atomic UTF-8 artifact writes: failed writes never truncate prior outputs."""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


@contextmanager
def atomic_text(destination: Path, *, newline: str | None = None) -> Iterator[TextIO]:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline=newline,
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            name = stream.name
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, destination)
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)
