"""Catalog search and event lookup (catalog-001..005)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.catalog.service import CatalogService, EventSummary, clean_query


def event(event_id: str, artist: str, venue: str) -> EventSummary:
    return EventSummary(
        event_id, f"{artist} live", artist, venue, datetime(2026, 11, 1, tzinfo=UTC), 2500, 100, 100
    )


class FakeCatalog:
    def __init__(self) -> None:
        self.events = [event("1", "Bulls Jazz", "Theatre 1"), event("2", "Tampa Symphony", "USF Arena")]
        self.searches: list[str] = []

    def list_active(self):
        return list(self.events)

    def search_active(self, term):
        self.searches.append(term)
        t = term.lower()
        return [e for e in self.events if t in e.artist.lower() or t in e.venue.lower()]

    def get_active(self, event_id):
        return next((e for e in self.events if e.id == event_id), None)


def test_no_query_lists_every_event():
    result = CatalogService(repository=FakeCatalog()).list_events()
    assert [e.id for e in result.events] == ["1", "2"]
    assert result.no_match is False


def test_search_matches_artist():
    result = CatalogService(repository=FakeCatalog()).list_events(query="jazz")
    assert [e.id for e in result.events] == ["1"]


def test_search_matches_venue():
    result = CatalogService(repository=FakeCatalog()).list_events(query="arena")
    assert [e.id for e in result.events] == ["2"]


def test_no_match_shows_message_and_full_list():
    result = CatalogService(repository=FakeCatalog()).list_events(query="polka")
    assert result.no_match is True
    assert result.query == "polka"
    assert [e.id for e in result.events] == ["1", "2"]


def test_query_is_trimmed_collapsed_and_bounded():
    assert clean_query("   ") is None
    assert clean_query("  usf   arena ") == "usf arena"
    assert len(clean_query("x" * 500)) == 100


def test_get_event_rejects_non_numeric_ids_without_hitting_storage():
    service = CatalogService(repository=FakeCatalog())
    assert service.get_event(event_id="1").artist == "Bulls Jazz"
    assert service.get_event(event_id="1 OR 1=1") is None
    assert service.get_event(event_id="999") is None
