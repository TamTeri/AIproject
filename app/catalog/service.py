"""Catalog: event list, artist/venue search, event page (catalog-001..007).

Pure logic over a repository port, so it is unit-tested without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

MAX_QUERY_LENGTH = 100


@dataclass(frozen=True)
class EventSummary:
    id: str
    title: str
    artist: str
    venue: str
    starts_at: datetime
    base_price_minor: int
    capacity: int
    available: int


@dataclass(frozen=True)
class SearchResult:
    events: list[EventSummary]
    query: str | None
    no_match: bool  # True -> show "no match" then the full list (catalog-005)


class CatalogRepository(Protocol):
    def list_active(self) -> list[EventSummary]: ...

    def search_active(self, term: str) -> list[EventSummary]: ...

    def get_active(self, event_id: str) -> EventSummary | None: ...


def clean_query(query: str | None) -> str | None:
    if query is None:
        return None
    cleaned = " ".join(str(query).split())[:MAX_QUERY_LENGTH]
    return cleaned or None


class CatalogService:
    def __init__(self, *, repository: CatalogRepository) -> None:
        self._repository = repository

    def list_events(self, *, query: str | None = None) -> SearchResult:
        """One search box matches artist OR venue (catalog-002/003)."""
        term = clean_query(query)
        if term is None:
            return SearchResult(self._repository.list_active(), None, False)
        matches = self._repository.search_active(term)
        if matches:
            return SearchResult(matches, term, False)
        return SearchResult(self._repository.list_active(), term, True)

    def get_event(self, *, event_id: str) -> EventSummary | None:
        event_id = str(event_id or "").strip()
        if not event_id.isdigit() or len(event_id) > 18:
            return None
        return self._repository.get_active(event_id)


__all__ = ["CatalogRepository", "CatalogService", "EventSummary", "SearchResult", "clean_query"]
