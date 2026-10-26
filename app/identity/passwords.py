from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Pbkdf2PasswordHasher:
    """Salted PBKDF2 password hashing with a self-describing stored format."""

    iterations: int = 310_000
    salt_bytes: int = 16
    digest_name: str = "sha256"

    def hash(self, password: str) -> str:
        if not isinstance(password, str):
            raise TypeError("password must be text")
        salt = secrets.token_bytes(self.salt_bytes)
        digest = hashlib.pbkdf2_hmac(
            self.digest_name,
            password.encode("utf-8"),
            salt,
            self.iterations,
        )
        return "$".join(
            (
                "pbkdf2_sha256",
                str(self.iterations),
                _encode(salt),
                _encode(digest),
            )
        )

    def verify(self, password: str, encoded_hash: str) -> bool:
        try:
            algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_text)
            salt = _decode(salt_text)
            expected = _decode(digest_text)
            actual = hashlib.pbkdf2_hmac(
                self.digest_name,
                password.encode("utf-8"),
                salt,
                iterations,
            )
        except (AttributeError, TypeError, ValueError):
            return False
        return hmac.compare_digest(actual, expected)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
