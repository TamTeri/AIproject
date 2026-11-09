"""Locale allowlist and request-locale resolution.

A raw header, query or cookie value is only ever *compared* with the allowlist;
the value that is stored, set in a cookie or used to pick a catalog is always one
of the SUPPORTED constants, never the input.
"""

from __future__ import annotations

import re

SUPPORTED: tuple[str, ...] = ("en", "es")  # add a language: a catalog file + a formatting table
DEFAULT_LOCALE = "en"
LANGUAGE_NAMES = {"en": "English", "es": "Español"}  # each in its own language
COOKIE_NAME = "eventhub_lang"

_MAX_HEADER = 500
_MAX_ITEMS = 20
_TAG = re.compile(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*")


def match_tag(tag: str | None) -> str | None:
    """Map "es", "ES-mx", "es_419"-style input to a supported locale, else None."""
    if not tag or len(tag) > 35:
        return None
    tag = tag.strip().replace("_", "-")
    if not _TAG.fullmatch(tag):
        return None
    primary = tag.split("-", 1)[0].lower()
    return primary if primary in SUPPORTED else None


def _from_accept_language(header: str | None) -> str | None:
    if not header:
        return None
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(header[:_MAX_HEADER].split(",")[:_MAX_ITEMS]):
        tag, _, params = part.partition(";")
        quality = 1.0
        params = params.strip().replace(" ", "")
        if params.lower().startswith("q="):
            try:
                quality = float(params[2:])
            except ValueError:
                continue
        supported = match_tag(tag.strip())
        if supported and 0 < quality <= 1:  # q=0 means "not acceptable"; nan/inf fail this
            ranked.append((-quality, index, supported))
    return min(ranked)[2] if ranked else None


def resolve_locale(
    query_lang: str | None = None, cookie: str | None = None, accept_language: str | None = None
) -> str:
    """?lang= > cookie > Accept-Language > "en". Unknown values fall back silently."""
    return (
        match_tag(query_lang) or match_tag(cookie) or _from_accept_language(accept_language) or DEFAULT_LOCALE
    )
