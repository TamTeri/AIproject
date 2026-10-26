from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.identity.contracts import AccountRecord, RegisterInput
from app.identity.passwords import Pbkdf2PasswordHasher
from app.identity.service import IdentityService


@dataclass
class FakeAccountRepository:
    records: dict[str, AccountRecord]

    def find_by_normalized_email(self, normalized_email: str) -> AccountRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.normalized_email == normalized_email
            ),
            None,
        )

    def find_by_id(self, account_id: str) -> AccountRecord | None:
        return self.records.get(account_id)

    def insert(
        self,
        *,
        name: str,
        normalized_email: str,
        password_hash: str,
        created_at: datetime,
    ) -> AccountRecord:
        account_id = f"acct-{len(self.records) + 1}"
        record = AccountRecord(
            account_id=account_id,
            name=name,
            normalized_email=normalized_email,
            password_hash=password_hash,
            created_at=created_at,
        )
        self.records[account_id] = record
        return record


def test_register_validates_and_persists_only_a_password_hash() -> None:
    repository = FakeAccountRepository(records={})
    service = IdentityService(
        account_repository=repository,
        password_hasher=Pbkdf2PasswordHasher(iterations=20_000),
    )
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)

    account = service.register(
        RegisterInput(
            name=" Ada Example ",
            email=" ADA@Example.COM ",
            password="Correct-Horse-Battery-7",
        ),
        now=now,
    )

    stored = repository.find_by_normalized_email("ada@example.com")
    assert stored is not None
    assert stored.password_hash != "Correct-Horse-Battery-7"
    assert service.password_hasher.verify("Correct-Horse-Battery-7", stored.password_hash)
    assert account.account_id == stored.account_id
    assert account.name == "Ada Example"
    assert account.email == "ada@example.com"
    assert not hasattr(account, "password")
    assert not hasattr(account, "password_hash")


@pytest.mark.parametrize(
    ("input_value", "message"),
    [
        (RegisterInput(name="", email="ada@example.com", password="Correct-Horse-Battery-7"), "name"),
        (RegisterInput(name="Ada", email="not-an-email", password="Correct-Horse-Battery-7"), "email"),
        (RegisterInput(name="Ada", email="ada@example.com", password="short"), "password"),
    ],
)
def test_register_rejects_invalid_identity_fields(
    input_value: RegisterInput,
    message: str,
) -> None:
    service = IdentityService(
        account_repository=FakeAccountRepository(records={}),
        password_hasher=Pbkdf2PasswordHasher(iterations=20_000),
    )

    with pytest.raises(ValueError, match=message):
        service.register(input_value, now=datetime(2030, 1, 1, tzinfo=timezone.utc))
