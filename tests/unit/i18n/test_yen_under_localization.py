"""system-023: the yen regression stays green through localization (4,500 JPY never becomes 45 JPY)."""

import re

import pytest

from app.i18n.formatting import format_money
from app.pricing.calculator import format_minor


@pytest.mark.requirement("system-023", "system-016")
@pytest.mark.parametrize("locale", ["en", "es"])
def test_yen_has_no_decimals_and_keeps_its_amount_in_every_locale(locale):
    text = format_money(4500, "JPY", 0, locale)
    assert int(re.sub(r"\D", "", text)) == 4500  # hand-derived literal, same digits in every locale
    assert not re.search(r"[.,]\d{2}\b", text)  # no 2-decimal formatting of a zero-decimal currency


@pytest.mark.requirement("system-023")
def test_english_locale_equals_the_unlocalized_formatter():
    assert format_money(4500, "JPY", 0, "en") == format_minor(4500, "JPY", 0) == "4,500 JPY"
