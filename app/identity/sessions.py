"""Server-side sessions (identity-006, system-008).

The browser only holds a random token (inside Flask's signed cookie). The
database stores its SHA-256 hash in ``account_sessions``. A session ends when:
- it has been idle longer than the SessionPolicy timeout (30 min temporary);
- it reaches its absolute lifetime; or
- the buyer logs out (revoked).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.identity.policy import SessionPolicy

ABSOLUTE_LIFETIME = timedelta(hours=12)  # [TEMPORARY_MVP_DEFAULT]


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    account_id: str
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class SessionRepository(Protocol):
    def insert(
        self, *, account_id: str, token_hash: str, created_at: datetime, expires_at: datetime
    ) -> None: ...

    def find_by_token_hash(self, token_hash: str) -> SessionRecord | None: ...

    def touch(self, session_id: str, *, now: datetime) -> None: ...

    def revoke(self, session_id: str, *, now: datetime) -> None: ...


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionService:
    def __init__(self, *, repository: SessionRepository, policy: SessionPolicy) -> None:
        self._repository = repository
        self._policy = policy

    def start(self, account_id: str, *, now: datetime) -> str:
        token = secrets.token_urlsafe(32)
        self._repository.insert(
            account_id=account_id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + ABSOLUTE_LIFETIME,
        )
        return token

    def resolve(self, token: str | None, *, now: datetime) -> str | None:
        """Return the account id for a live session, refreshing its idle clock."""
        if not token or not isinstance(token, str) or len(token) > 256:
            return None
        record = self._repository.find_by_token_hash(hash_token(token))
        if record is None or record.revoked_at is not None:
            return None
        if now >= record.expires_at or now - record.last_seen_at > self._policy.idle_timeout:
            self._repository.revoke(record.session_id, now=now)
            return None
        self._repository.touch(record.session_id, now=now)
        return record.account_id

    def end(self, token: str | None, *, now: datetime) -> None:
        if not token or not isinstance(token, str):
            return
        record = self._repository.find_by_token_hash(hash_token(token))
        if record is not None and record.revoked_at is None:
            self._repository.revoke(record.session_id, now=now)


__all__ = ["ABSOLUTE_LIFETIME", "SessionRecord", "SessionRepository", "SessionService", "hash_token"]
