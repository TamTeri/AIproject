"""The one definition of "looks like a database id" (BIGINT, so at most 18 digits).

Dependency-free so domain services can use it without importing the DB layer.
"""

from __future__ import annotations


def is_db_id(text: str) -> bool:
    # isascii(): str.isdigit() also accepts "²" and "①", which int() rejects (Part 5, ST-20/21).
    return text.isascii() and text.isdigit() and len(text) <= 18
