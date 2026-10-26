from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.identity.contracts import AccountRecord


class DuplicateEmailError(RuntimeError):
    """Raised by an account adapter when its schema uniqueness constraint wins a race."""


class AccountRepository(Protocol):
    """Persistence port; a DB adapter is supplied only after the shared schema contract."""

    def find_by_normalized_email(self, normalized_email: str) -> AccountRecord | None: ...

    def find_by_id(self, account_id: str) -> AccountRecord | None: ...

    def insert(
        self,
        *,
        name: str,
        normalized_email: str,
        password_hash: str,
        created_at: datetime,
    ) -> AccountRecord: ...
