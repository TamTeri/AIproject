"""Regional date and money display. Display only: never changes a stored/charged amount."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.pricing.calculator import format_minor

from .locales import DEFAULT_LOCALE

_ES_DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")  # Monday first
_ES_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
# (thousands, decimal) separators; an unlisted locale uses English.
_SEPARATORS = {"en": (",", "."), "es": (".", ",")}
_MONEY_TEXT = re.compile(r"(-?)(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d+))? ([A-Z]{3})")


def format_when(value: Any, locale: str = DEFAULT_LOCALE, style: str = "datetime") -> str:
    """en: "Sun, Nov 1, 2026 · 7:00 PM"; es: "dom, 1 nov 2026 · 19:00"."""
    if not isinstance(value, datetime):
        return "" if value is None else str(value)
    if locale == "es":
        time_text = f"{value.hour:02d}:{value.minute:02d}"
        if style == "time":
            return time_text
        day, month = _ES_DAYS[value.weekday()], _ES_MONTHS[value.month - 1]
        return f"{day}, {value.day} {month} {value.year} · {time_text}"
    time_text = value.strftime("%I:%M %p").lstrip("0")
    if style == "time":
        return time_text
    return f"{value.strftime('%a, %b')} {value.day}, {value.year} · {time_text}"


def format_money_text(text: Any, locale: str = DEFAULT_LOCALE) -> Any:
    """Re-punctuate an already formatted "1,234.50 EUR". Anything else passes through unchanged.

    Only separators move: the digits and currency code are kept as they are, so the
    amount a locale shows is always the amount that was charged.
    """
    if locale == DEFAULT_LOCALE or not isinstance(text, str):
        return text
    m = _MONEY_TEXT.fullmatch(text)
    if not m:
        return text
    sign, integer, fraction, code = m.groups()
    thousands, decimal = _SEPARATORS.get(locale, _SEPARATORS[DEFAULT_LOCALE])
    grouped = f"{int(integer.replace(',', '')):,}".replace(",", thousands)
    return f"{sign}{grouped}{decimal + fraction if fraction else ''} {code}"


def format_money(amount_minor: int, code: str, exponent: int, locale: str = DEFAULT_LOCALE) -> str:
    """Same digits as pricing.format_minor ("3,753 JPY" / "25.00 USD"); es swaps the separators.

    The exponent comes from the currency (JPY 0), so yen never shows decimals.
    """
    return format_money_text(format_minor(amount_minor, code, exponent), locale)
