"""PostgreSQL adapter for the catalog. Availability comes from the
inventory-owned ``event_availability`` view (capacity - sold - active holds)."""

from __future__ import annotations

from app.catalog.service import EventSummary
from app.db.transaction import SqlTransaction, db_id

_SELECT = """
    SELECT e.id, e.title, e.artist, e.venue, e.starts_at, e.base_price_minor, e.capacity,
           GREATEST(a.available_quantity, 0) AS available
    FROM events e
    JOIN event_availability a ON a.event_id = e.id
    WHERE e.status = 'active'
"""


def _summary(row: dict) -> EventSummary:
    return EventSummary(
        id=str(row["id"]),
        title=row["title"],
        artist=row["artist"],
        venue=row["venue"],
        starts_at=row["starts_at"],
        base_price_minor=int(row["base_price_minor"]),
        capacity=int(row["capacity"]),
        available=int(row["available"]),
    )


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class PostgresCatalogRepository:
    def __init__(self, tx: SqlTransaction) -> None:
        self._tx = tx

    def list_active(self) -> list[EventSummary]:
        return [_summary(r) for r in self._tx.fetch_all(_SELECT + " ORDER BY e.starts_at, e.id")]

    def search_active(self, term: str) -> list[EventSummary]:
        rows = self._tx.fetch_all(
            _SELECT
            + """
              AND (e.artist ILIKE :pattern ESCAPE '\\' OR e.venue ILIKE :pattern ESCAPE '\\')
            ORDER BY e.starts_at, e.id
            """,
            {"pattern": _like(term)},
        )
        return [_summary(r) for r in rows]

    def get_active(self, event_id: str) -> EventSummary | None:
        key = db_id(event_id)
        if key is None:
            return None
        row = self._tx.fetch_one(_SELECT + " AND e.id = :id", {"id": key})
        return _summary(row) if row else None
