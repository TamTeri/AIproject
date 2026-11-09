"""Message catalogs: text only (no amounts, no HTML), named {placeholders} only."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .locales import DEFAULT_LOCALE, SUPPORTED

_DIR = Path(__file__).parent
# File names come from the SUPPORTED allowlist, never from request input.
CATALOGS: dict[str, dict[str, str]] = {
    code: json.loads((_DIR / f"{code}.json").read_text(encoding="utf-8")) for code in SUPPORTED
}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


def translate(key: str, locale: str = DEFAULT_LOCALE, **values: object) -> str:
    """Look up key (falling back to English, then the key) and fill {name} slots.

    Plain substitution rather than str.format, so a message can never reach into
    an object's attributes. The result is plain text; Jinja autoescape escapes it.
    """
    text = CATALOGS.get(locale, {}).get(key)
    if text is None:
        text = CATALOGS[DEFAULT_LOCALE].get(key, key)
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
