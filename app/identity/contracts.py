from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RegisterInput:
    name: str
    email: str
    password: str


@dataclass(frozen=True)
class LoginInput:
    email: str
    password: str


@dataclass(frozen=True)
class AccountRecord:
    account_id: str
    name: str
    normalized_email: str
    password_hash: str
    created_at: datetime


@dataclass(frozen=True)
class PublicAccount:
    account_id: str
    name: str
    email: str


@dataclass(frozen=True)
class Principal:
    account_id: str
    name: str
    email: str
