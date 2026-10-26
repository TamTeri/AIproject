from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("email must be text")
    normalized = email.strip().casefold()
    if not normalized or not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("email must be a valid address")
    return normalized


@dataclass(frozen=True)
class SessionPolicy:
    """Session expiry policy supplied by the composition root."""

    idle_timeout: timedelta
    label: str = "configured"

    @classmethod
    def temporary_mvp(cls) -> "SessionPolicy":
        return cls(
            idle_timeout=timedelta(minutes=30),
            label="TEMPORARY_SESSION_IDLE_TIMEOUT_30_MINUTES",
        )

    @classmethod
    def from_values(
        cls,
        values: Mapping[str, object],
        *,
        environment: str,
    ) -> "SessionPolicy":
        raw_timeout = values.get("EVENTHUB_SESSION_IDLE_TIMEOUT_SECONDS")
        if raw_timeout is None:
            if environment in {"local", "development"}:
                return cls.temporary_mvp()
            raise ValueError(
                "EVENTHUB_SESSION_IDLE_TIMEOUT_SECONDS is required outside local/development"
            )
        try:
            seconds = int(str(raw_timeout).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("session idle timeout must be a positive integer number of seconds") from exc
        if seconds <= 0:
            raise ValueError("session idle timeout must be a positive integer number of seconds")
        return cls(idle_timeout=timedelta(seconds=seconds), label="configured")
