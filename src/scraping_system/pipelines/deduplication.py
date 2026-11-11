"""Run-scoped exact deduplication using stable record identities."""


class Deduplicator:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def is_duplicate(self, record_id: str) -> bool:
        if record_id in self.seen:
            return True
        self.seen.add(record_id)
        return False
