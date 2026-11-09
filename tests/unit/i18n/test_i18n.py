"""system-020/021/022: locale resolution, catalogs, regional date and money formatting."""

from __future__ import annotations

import re
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.i18n import format_money, format_money_text, format_when, resolve_locale, translate
from app.i18n.catalog import CATALOGS, placeholders
from app.i18n.locales import SUPPORTED
from app.identity.contracts import Principal
from app.pricing.calculator import format_minor
from app.web import create_web_app

# ------------------------------------------------------------------ resolver


@pytest.mark.requirement("system-020")
@pytest.mark.parametrize(
    ("query", "cookie", "header", "expected"),
    [
        (None, None, None, "en"),
        ("es", "en", "en", "es"),  # ?lang= beats cookie and header
        (None, "es", "en", "es"),  # cookie beats header
        (None, None, "es-MX,es;q=0.9,en;q=0.8", "es"),
        (None, None, "fr, de;q=0.9", "en"),  # nothing supported: silent fallback
        (None, None, "fr;q=0.9, es;q=0.5, en;q=0.1", "es"),
        (None, None, "en;q=0.2, es;q=0.8", "es"),  # q-values order the choice
        (None, None, "es;q=0, en", "en"),  # q=0 is "not acceptable"
        (None, None, "es;q=nan", "en"),
        (None, None, "es;q=9", "en"),
        (None, None, "*", "en"),
        ("ES-mx", None, None, "es"),
        ("xx", "es", None, "es"),  # unknown ?lang= falls through to the next source
    ],
)
def test_resolution_order_and_fallback(query, cookie, header, expected):
    assert resolve_locale(query, cookie, header) == expected


@pytest.mark.requirement("system-020")
@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..\\..\\windows",
        "es/../en",
        "es\r\nSet-Cookie: x=1",
        "es\x00",
        "%2e%2e",
        "e" * 5000,
        "",
    ],
)
def test_hostile_values_never_leave_the_allowlist(hostile):
    for result in (
        resolve_locale(hostile),
        resolve_locale(None, hostile),
        resolve_locale(None, None, hostile),
        resolve_locale(None, None, f"{hostile};q=1, en"),
    ):
        assert result in SUPPORTED
    assert resolve_locale(hostile) == "en"


@pytest.mark.requirement("system-020")
def test_oversized_accept_language_is_ignored_past_the_cap():
    assert resolve_locale(None, None, "x," * 400 + "es") == "en"


# ------------------------------------------------------------------ catalogs


@pytest.mark.requirement("system-020")
def test_catalogs_have_identical_keys_and_placeholders():
    assert set(CATALOGS["en"]) == set(CATALOGS["es"])
    for key, text in CATALOGS["en"].items():
        assert placeholders(text) == placeholders(CATALOGS["es"][key]), key


@pytest.mark.requirement("system-020")
def test_catalogs_are_plain_text_without_markup_or_amounts():
    for locale, catalog in CATALOGS.items():
        for key, text in catalog.items():
            assert isinstance(text, str) and text.strip(), (locale, key)
            assert not re.search(r"[<>&]", text), (locale, key)
            assert "{{" not in text and "%(" not in text, (locale, key)
            assert not re.search(r"\d[.,]\d|[$€¥£]", text), (locale, key)  # no formatted amounts
            assert not re.search(r"\{\w*[^\w}][^}]*\}", text), (locale, key)  # named slots only


@pytest.mark.requirement("system-020")
def test_translate_fills_named_slots_and_falls_back():
    assert translate("nav_logout", "es", name="Ana") == "Cerrar sesión (Ana)"
    assert translate("nav_logout", "xx", name="Ana") == "Log out (Ana)"  # unknown locale -> English
    assert translate("no_such_key", "es") == "no_such_key"
    # no attribute access through a placeholder
    assert translate("nav_logout", "en", name=SimpleNamespace(secret="x")).startswith("Log out (namespace")


# ---------------------------------------------------------------- formatting

MOMENT = datetime(2026, 11, 1, 19, 5)  # a Sunday


@pytest.mark.requirement("system-021")
def test_dates_per_locale():
    assert format_when(MOMENT, "en") == "Sun, Nov 1, 2026 · 7:05 PM"
    assert format_when(MOMENT, "en", "time") == "7:05 PM"
    assert format_when(MOMENT, "es") == "dom, 1 nov 2026 · 19:05"
    assert format_when(MOMENT, "es", "time") == "19:05"
    assert format_when(None, "es") == ""
    assert format_when("already text", "es") == "already text"


@pytest.mark.requirement("system-022")
@pytest.mark.parametrize(
    ("minor", "code", "exp", "en", "es"),
    [
        (2500, "USD", 2, "25.00 USD", "25,00 USD"),
        (123456, "EUR", 2, "1,234.56 EUR", "1.234,56 EUR"),
        (3753, "JPY", 0, "3,753 JPY", "3.753 JPY"),  # yen never gets decimals
        (450, "JPY", 0, "450 JPY", "450 JPY"),
        (0, "JPY", 0, "0 JPY", "0 JPY"),
        (123456789, "USD", 2, "1,234,567.89 USD", "1.234.567,89 USD"),
    ],
)
def test_money_per_locale(minor, code, exp, en, es):
    assert format_money(minor, code, exp, "en") == en == format_minor(minor, code, exp)
    assert format_money(minor, code, exp, "es") == es
    if code == "JPY":
        assert not re.search(r"[.,]\d{1,2}\b(?! )", format_money(minor, code, exp, "es").split()[0])


@pytest.mark.requirement("system-022")
@pytest.mark.parametrize("locale", SUPPORTED)
@pytest.mark.parametrize("minor", [0, 1, 99, 100, 3753, 123456, 98765432101])
def test_locale_never_changes_the_amount(minor, locale):
    """Stripping separators from the localized text gives the same number as English."""
    for code, exp in (("USD", 2), ("JPY", 0), ("KWD", 3)):
        english = format_minor(minor, code, exp)
        shown = format_money(minor, code, exp, locale)
        digits = re.sub(r"\D", "", shown.split()[0])
        assert digits == re.sub(r"\D", "", english.split()[0])
        assert shown.split()[1] == code


@pytest.mark.requirement("system-022")
def test_money_text_passes_through_anything_unrecognised():
    for value in (None, "", "n/a", "12 dollars", "1,23 EUR", 42):
        assert format_money_text(value, "es") == value
    assert format_money_text("-4.60 EUR", "es") == "-4,60 EUR"


# ------------------------------------------------------- Flask integration


class _Fake:
    """Just enough service surface for the checkout, orders and events pages."""

    def __init__(self) -> None:
        buyer = Principal("buyer-1", "Buyer", "buyer@usf.edu", preferred_currency="JPY")
        self.identity = SimpleNamespace(resolve_session=lambda *, token: buyer if token == "t" else None)
        event = {
            "id": "e1", "title": "Night", "artist": "A", "venue": "Hall",
            "starts_at": datetime(2026, 11, 1, 19, 0), "available": 3, "base_price_minor": 2500,
        }  # fmt: skip
        self.catalog = SimpleNamespace(
            list_events=lambda *, query=None: {"events": [event], "query": None, "no_match": False},
            get_event=lambda *, event_id: event,
        )
        self.pricing = SimpleNamespace(
            currencies=lambda: ["JPY", "USD"], base_price_display=lambda *, base_price_minor: "25.00 USD"
        )
        self.orders = SimpleNamespace(list_for_buyer=lambda *, buyer_id: [], get_for_buyer=lambda **_: ORDER)
        self.checkout = self.purchase = SimpleNamespace(review=lambda **_: HOLD)


ORDER = SimpleNamespace(
    id="o1", event_title="Night", artist="A", venue="Hall", starts_at=datetime(2026, 11, 1, 19, 0),
    quantity=2, currency="JPY", exchange_rate_display="150", subtotal="7,506 JPY", discount="750 JPY",
    discount_applied=True, total="6,756 JPY", created_at=datetime(2026, 10, 1, 9, 30), list_price="25.00 USD",
)  # fmt: skip
HOLD = SimpleNamespace(
    hold_id="h1", event_id="e1", event_title="Night", quantity=2, currency="JPY",
    subtotal="7,506 JPY", discount="750 JPY", discount_applied=True, total="6,756 JPY",
    exchange_rate="150", expires_at=datetime(2026, 11, 1, 12, 10), status="active", list_price="25.00 USD",
)  # fmt: skip


@pytest.fixture
def client():
    app = create_web_app(services=_Fake(), config={"TESTING": True, "SECRET_KEY": "t"})
    c = app.test_client()
    with c.session_transaction() as s:
        s["session_token"] = "t"
        s["csrf_token"] = "c"
    return c


@pytest.mark.requirement("system-020")
def test_default_is_english_and_switcher_is_present(client):
    html = client.get("/events").get_data(as_text=True)
    assert '<html lang="en">' in html
    assert "Order history" in html
    assert 'href="/events?lang=es"' in html
    assert "Quick Buy one ticket in JPY, your saved home currency" in html


@pytest.mark.requirement("system-020")
def test_lang_query_sets_cookie_and_translates(client):
    response = client.get("/events?lang=es")
    html = response.get_data(as_text=True)
    assert '<html lang="es">' in html
    assert "Historial de pedidos" in html
    assert "dom, 1 nov 2026 · 19:00" in html
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith("eventhub_lang=es;") and "HttpOnly" in cookie
    assert "Accept-Language" in response.headers["Vary"]
    # the cookie now carries the choice; an Accept-Language of English does not override it
    follow = client.get("/events", headers={"Accept-Language": "en"})
    assert '<html lang="es">' in follow.get_data(as_text=True)


@pytest.mark.requirement("system-020")
@pytest.mark.parametrize("hostile", ["../../etc/passwd", "xx", "es%0d%0aX-Evil: 1", ""])
def test_bad_lang_is_ignored_and_never_reflected(client, hostile):
    response = client.get("/events", query_string={"lang": hostile})
    assert response.status_code == 200
    assert '<html lang="en">' in response.get_data(as_text=True)
    assert "Set-Cookie" not in response.headers
    assert "evil" not in str(response.headers).lower()


@pytest.mark.requirement("system-020")
def test_accept_language_is_used_without_a_cookie(client):
    html = client.get("/events", headers={"Accept-Language": "es-MX,es;q=0.9"}).get_data(as_text=True)
    assert '<html lang="es">' in html


@pytest.mark.requirement("system-022")
@pytest.mark.parametrize("path", ["/checkout/h1", "/orders/o1"])
def test_same_underlying_amounts_in_every_locale(client, path):
    """Yen stays whole yen and the digits shown are the stored digits, in both languages."""
    en = client.get(path, query_string={"lang": "en"}).get_data(as_text=True)
    es = client.get(path, query_string={"lang": "es"}).get_data(as_text=True)
    assert "6,756 JPY" in en and "6.756 JPY" in es
    assert "7,506 JPY" in en and "7.506 JPY" in es
    assert "6,756 JPY" not in es
    assert not re.search(r"\d[.,]\d{2} JPY", en + es)  # no decimals on yen

    def digits(html):
        return re.findall(r"amount\">([^<]+)<", html)

    assert [re.sub(r"\D", "", x) for x in digits(en)] == [re.sub(r"\D", "", x) for x in digits(es)]
