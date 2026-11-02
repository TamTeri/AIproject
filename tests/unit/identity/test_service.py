from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.identity.contracts import AccountRecord, RegisterInput
from app.identity.passwords import Pbkdf2PasswordHasher
from app.identity.service import IdentityService


@dataclass
class FakeAccountRepository:
    records: dict[str, AccountRecord]

    def find_by_normalized_email(self, normalized_email: str) -> AccountRecord | None:
        return next(
            (record for record in self.records.values() if record.normalized_email == normalized_email),
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

    def update_email(self, account_id: str, normalized_email: str) -> None:
        from dataclasses import replace

        self.records[account_id] = replace(self.records[account_id], normalized_email=normalized_email)


def test_register_validates_and_persists_only_a_password_hash() -> None:
    repository = FakeAccountRepository(records={})
    service = IdentityService(
        account_repository=repository,
        password_hasher=Pbkdf2PasswordHasher(iterations=20_000),
    )
    now = datetime(2030, 1, 1, tzinfo=UTC)

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
        service.register(input_value, now=datetime(2030, 1, 1, tzinfo=UTC))


# ---- login (identity-003/004/005)

from app.identity.contracts import LoginInput  # noqa: E402
from app.identity.service import EmailAlreadyRegistered, InvalidCredentials  # noqa: E402


def _service_with_account():
    repository = FakeAccountRepository(records={})
    service = IdentityService(
        account_repository=repository,
        password_hasher=Pbkdf2PasswordHasher(iterations=20_000),
    )
    service.register(
        RegisterInput(name="Ada", email="ada@usf.edu", password="Correct-Horse-Battery-7"),
        now=datetime(2030, 1, 1, tzinfo=UTC),
    )
    return service


def test_login_with_valid_credentials_returns_principal_without_secrets():
    principal = _service_with_account().authenticate(
        LoginInput(email=" ADA@usf.edu ", password="Correct-Horse-Battery-7")
    )
    assert principal.email == "ada@usf.edu"
    assert principal.role == "buyer"
    assert principal.is_admin is False
    assert not hasattr(principal, "password_hash")


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("ada@usf.edu", "wrong-password"),
        ("nobody@usf.edu", "Correct-Horse-Battery-7"),
        ("not-an-email", "Correct-Horse-Battery-7"),
        ("ada@usf.edu", ""),
    ],
)
def test_login_failures_all_look_the_same(email, password):
    with pytest.raises(InvalidCredentials, match="invalid email or password"):
        _service_with_account().authenticate(LoginInput(email=email, password=password))


def test_duplicate_email_is_rejected_case_insensitively():
    service = _service_with_account()
    with pytest.raises(EmailAlreadyRegistered):
        service.register(
            RegisterInput(name="Ada 2", email="ADA@USF.EDU", password="another-password"),
            now=datetime(2030, 1, 1, tzinfo=UTC),
        )


def test_people_anywhere_can_register_with_any_email_domain():
    service = _service_with_account()
    account = service.register(
        RegisterInput(name="Kenji", email="kenji@example.jp", password="another-password"),
        now=datetime(2030, 1, 1, tzinfo=UTC),
    )
    assert account.email == "kenji@example.jp"


# ------------------------------------------------------- identity-014 (Call 5)


def _service_with(*emails: str) -> tuple[IdentityService, list[str]]:
    service = IdentityService(
        account_repository=FakeAccountRepository(records={}),
        password_hasher=Pbkdf2PasswordHasher(iterations=20_000),
    )
    now = datetime(2030, 1, 1, tzinfo=UTC)
    ids = [
        service.register(RegisterInput(name="Kenji", email=e, password="password-123"), now=now).account_id
        for e in emails
    ]
    return service, ids


def test_change_email_needs_the_current_password() -> None:
    from app.identity.service import WrongCurrentPassword

    service, (kenji,) = _service_with("kenji@usf.edu")
    with pytest.raises(WrongCurrentPassword):
        service.change_email(account_id=kenji, new_email="kenji@gmail.com", current_password="wrong-pass")
    assert service.principal(kenji).email == "kenji@usf.edu"


def test_change_email_normalizes_and_is_what_later_lookups_see() -> None:
    service, (kenji,) = _service_with("kenji@usf.edu")
    principal = service.change_email(
        account_id=kenji, new_email="  Kenji@Gmail.COM ", current_password="password-123"
    )
    assert principal.email == "kenji@gmail.com"
    assert service.principal(kenji).email == "kenji@gmail.com"  # pricing-011 reads this email


def test_change_email_refuses_an_address_another_account_uses() -> None:
    from app.identity.service import EmailAlreadyRegistered

    service, (kenji, _friend) = _service_with("kenji@usf.edu", "friend@usf.edu")
    with pytest.raises(EmailAlreadyRegistered):
        service.change_email(account_id=kenji, new_email="FRIEND@usf.edu", current_password="password-123")


def test_change_email_rejects_an_invalid_address() -> None:
    from app.identity.service import RegistrationValidationError

    service, (kenji,) = _service_with("kenji@usf.edu")
    with pytest.raises(RegistrationValidationError):
        service.change_email(account_id=kenji, new_email="not-an-email", current_password="password-123")
