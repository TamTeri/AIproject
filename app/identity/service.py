from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.identity.contracts import AccountRecord, LoginInput, Principal, PublicAccount, RegisterInput
from app.identity.passwords import Pbkdf2PasswordHasher
from app.identity.policy import normalize_email
from app.identity.repository import AccountRepository, DuplicateEmailError


class RegistrationValidationError(ValueError):
    """Raised when registration data does not satisfy the identity boundary."""


class EmailAlreadyRegistered(ValueError):
    """Raised when the normalized email is already owned by an account."""


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str:
        ...

    def verify(self, password: str, encoded_hash: str) -> bool:
        ...


class IdentityService:
    def __init__(
        self,
        *,
        account_repository: AccountRepository,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.account_repository = account_repository
        self.password_hasher = password_hasher or Pbkdf2PasswordHasher()

    def register(self, input_value: RegisterInput, *, now: datetime) -> PublicAccount:
        name = _validate_name(input_value.name)
        normalized_email = _validate_email(input_value.email)
        password = _validate_password(input_value.password)

        if self.account_repository.find_by_normalized_email(normalized_email) is not None:
            raise EmailAlreadyRegistered("email is already registered")

        password_hash = self.password_hasher.hash(password)
        try:
            record = self.account_repository.insert(
                name=name,
                normalized_email=normalized_email,
                password_hash=password_hash,
                created_at=now,
            )
        except DuplicateEmailError as exc:
            raise EmailAlreadyRegistered("email is already registered") from exc
        return _public_account(record)


def _validate_name(value: str) -> str:
    if not isinstance(value, str):
        raise RegistrationValidationError("name must be text")
    name = value.strip()
    if not name:
        raise RegistrationValidationError("name must not be blank")
    if len(name) > 200:
        raise RegistrationValidationError("name must be at most 200 characters")
    return name


def _validate_email(value: str) -> str:
    try:
        normalized = normalize_email(value)
    except ValueError as exc:
        raise RegistrationValidationError(str(exc)) from exc
    if len(normalized) > 320:
        raise RegistrationValidationError("email must be at most 320 characters")
    return normalized


def _validate_password(value: str) -> str:
    if not isinstance(value, str):
        raise RegistrationValidationError("password must be text")
    if len(value) < 8:
        raise RegistrationValidationError("password must be at least 8 characters")
    if len(value) > 1024:
        raise RegistrationValidationError("password must be at most 1024 characters")
    return value


def _public_account(record: AccountRecord) -> PublicAccount:
    return PublicAccount(
        account_id=record.account_id,
        name=record.name,
        email=record.normalized_email,
    )
