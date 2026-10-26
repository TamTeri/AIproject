"""Server-side sessions: idle timeout, absolute lifetime, logout (identity-006, system-008)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.identity.policy import SessionPolicy
from app.identity.sessions import ABSOLUTE_LIFETIME, SessionRecord, SessionService, hash_token

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class FakeSessions:
    def __init__(self) -> None:
        self.rows: dict[str, SessionRecord] = {}
        self.hashes: dict[str, str] = {}

    def insert(self, *, account_id, token_hash, created_at, expires_at):
        session_id = str(len(self.rows) + 1)
        self.rows[session_id] = SessionRecord(session_id, account_id, created_at, expires_at, None)
        self.hashes[token_hash] = session_id

    def find_by_token_hash(self, token_hash):
        session_id = self.hashes.get(token_hash)
        return self.rows.get(session_id) if session_id else None

    def touch(self, session_id, *, now):
        self.rows[session_id] = replace(self.rows[session_id], last_seen_at=now)

    def revoke(self, session_id, *, now):
        self.rows[session_id] = replace(self.rows[session_id], revoked_at=now)


def make():
    repo = FakeSessions()
    return repo, SessionService(repository=repo, policy=SessionPolicy.temporary_mvp())


def test_token_is_random_and_only_its_hash_is_stored():
    repo, sessions = make()
    token = sessions.start("42", now=T0)
    assert len(token) >= 32
    assert token not in repo.hashes
    assert hash_token(token) in repo.hashes


def test_activity_keeps_the_session_alive():
    _, sessions = make()
    token = sessions.start("42", now=T0)
    for minute in (20, 40, 60, 80):
        assert sessions.resolve(token, now=T0 + timedelta(minutes=minute)) == "42"


def test_session_expires_after_thirty_idle_minutes():
    _, sessions = make()
    token = sessions.start("42", now=T0)
    assert sessions.resolve(token, now=T0 + timedelta(minutes=31)) is None
    # and it stays dead even if used again quickly
    assert sessions.resolve(token, now=T0 + timedelta(minutes=32)) is None


def test_session_has_an_absolute_lifetime():
    _, sessions = make()
    token = sessions.start("42", now=T0)
    now = T0
    while now < T0 + ABSOLUTE_LIFETIME - timedelta(minutes=10):
        now += timedelta(minutes=10)
        assert sessions.resolve(token, now=now) == "42"
    assert sessions.resolve(token, now=T0 + ABSOLUTE_LIFETIME) is None


def test_logout_revokes_the_session():
    _, sessions = make()
    token = sessions.start("42", now=T0)
    sessions.end(token, now=T0)
    assert sessions.resolve(token, now=T0) is None


def test_garbage_tokens_are_ignored():
    _, sessions = make()
    for token in (None, "", "x" * 300, "unknown-token"):
        assert sessions.resolve(token, now=T0) is None
