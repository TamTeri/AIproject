"""Part 7: EventHub configured to run in Spanish (system-024..027, ADR-011).

Web boundary with fake services, no database. The browser in these tests asks for
English (Accept-Language: en-US), so a Spanish page proves the *configuration* chose it.
"""

from __future__ import annotations

import ast
import html as html_lib
import re
from pathlib import Path

import pytest

from app.i18n.catalog import CATALOGS, placeholders
from app.identity.contracts import Principal
from app.web import OUTCOME_ERRORS, SERVICE_ERROR_KEYS, create_web_app
from tests.contract.test_api_v1_routes import EVENT, CatalogFake, ServicesFake, login_as

ROOT = Path(__file__).resolve().parents[2]
ENGLISH_BROWSER = {"Accept-Language": "en-US,en;q=0.9"}
SPANISH_BROWSER = {"Accept-Language": "es-MX,es;q=0.9"}
# Names that are not catalog words, so a user's name is never mistaken for English UI text.
ANA = Principal("buyer-1", "Ana", "buyer@usf.edu", preferred_currency="EUR")
ROSA = Principal("admin-1", "Rosa", "admin@eventhub.test", role="administrator")


def make_client(language: str | None):
    services = ServicesFake(catalog=CatalogFake(events=[dict(EVENT)]))
    services.identity.tokens = {"buyer-token": ANA, "admin-token": ROSA}
    config = {"TESTING": True, "SECRET_KEY": "test"}
    if language is not None:
        config["EVENTHUB_LANGUAGE"] = language
    return create_web_app(services=services, config=config).test_client(), services


def menu(page: str) -> list[str]:
    """The top-level menu entries, in order, as a person reads them."""
    nav = re.search(r"<nav[^>]*>(.*?)</nav>", page, re.S).group(1)
    items = re.findall(r"<(?:a|button)\b[^>]*>(.*?)</(?:a|button)>", nav, re.S)
    return [html_lib.unescape(" ".join(item.split())) for item in items]


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return html_lib.unescape(" ".join(re.sub(r"<[^>]+>", " ", page).split()))


def english_left(page: str) -> list[str]:
    """English catalog text (that differs from the Spanish) still visible on a page."""
    text = visible_text(page)
    left = []
    for key, english in CATALOGS["en"].items():
        if english == CATALOGS["es"][key]:
            continue  # "Total", "Subtotal": the same word in both languages
        for part in re.split(r"\{\w+\}", english):
            part = part.strip(" ().,:")
            if len(re.sub(r"[^A-Za-z]", "", part)) >= 4 and re.search(
                rf"(?<![A-Za-z]){re.escape(part)}(?![A-Za-z])", text
            ):
                left.append(f"{key}: {part}")
    return left


# ---------------------------------------------------- system-024: the setting


@pytest.mark.requirement("system-024", "system-026")
def test_configured_spanish_shows_the_guest_menu_in_spanish_to_an_english_browser():
    client, _ = make_client("es")
    response = client.get("/events", headers=ENGLISH_BROWSER)
    page = response.get_data(as_text=True)
    assert '<html lang="es">' in page
    assert menu(page) == ["EventHub", "Eventos", "Historial de pedidos", "Iniciar sesión", "Registrarse"]
    assert '<nav aria-label="Principal">' in page
    assert "Idioma:" in visible_text(page)
    cookies = " ".join(response.headers.getlist("Set-Cookie"))
    assert "eventhub_lang" not in cookies  # the configuration is not a visitor's choice: nothing to remember


@pytest.mark.requirement("system-026")
def test_configured_spanish_menu_for_a_buyer_and_an_administrator():
    client, _ = make_client("es")
    login_as(client, "buyer-token")
    assert menu(client.get("/events", headers=ENGLISH_BROWSER).get_data(as_text=True)) == [
        "EventHub", "Eventos", "Historial de pedidos", "Cuenta", "Cerrar sesión (Ana)",
    ]  # fmt: skip
    login_as(client, "admin-token")
    assert menu(client.get("/events", headers=ENGLISH_BROWSER).get_data(as_text=True)) == [
        "EventHub", "Eventos", "Historial de pedidos", "Cuenta", "Administración", "Cerrar sesión (Rosa)",
    ]  # fmt: skip


@pytest.mark.requirement("system-024", "system-026")
def test_configured_english_shows_english_to_a_spanish_browser():
    client, _ = make_client("en")
    page = client.get("/events", headers=SPANISH_BROWSER).get_data(as_text=True)
    assert '<html lang="en">' in page
    assert menu(page) == ["EventHub", "Events", "Order history", "Log in", "Register"]


@pytest.mark.requirement("system-020", "system-024")
@pytest.mark.parametrize("not_configured", [None, "", "   "])
def test_not_configured_follows_the_browser_as_before(not_configured):
    client, _ = make_client(not_configured)
    assert '<html lang="es">' in client.get("/events", headers=SPANISH_BROWSER).get_data(as_text=True)
    assert '<html lang="en">' in client.get("/events", headers=ENGLISH_BROWSER).get_data(as_text=True)
    assert '<html lang="en">' in client.get("/events").get_data(as_text=True)


@pytest.mark.requirement("system-020", "system-024")
def test_a_visitors_choice_beats_the_configured_language_and_is_remembered():
    client, _ = make_client("es")
    chosen = client.get("/events?lang=en", headers=ENGLISH_BROWSER)
    assert chosen.headers["Set-Cookie"].startswith("eventhub_lang=en;")
    assert menu(chosen.get_data(as_text=True))[1] == "Events"
    assert '<html lang="en">' in client.get("/login").get_data(as_text=True)  # the cookie carries it
    assert '<html lang="es">' in client.get("/login?lang=es").get_data(as_text=True)


@pytest.mark.requirement("system-025")
@pytest.mark.parametrize("bad", ["fr", "spanish", "es-MX"])
def test_an_app_built_with_an_unsupported_language_is_refused(bad):
    with pytest.raises(ValueError, match="EVENTHUB_LANGUAGE must be one of: en, es"):
        create_web_app(
            services=ServicesFake(catalog=CatalogFake(events=[])), config={"EVENTHUB_LANGUAGE": bad}
        )


# ------------------------------------------- system-027: every page in Spanish

PAGES = [
    (None, "/events", 200),
    (None, "/events/event-1", 200),
    (None, "/login", 200),
    (None, "/register", 200),
    (None, "/no-such-page", 404),
    ("buyer-token", "/events", 200),
    ("buyer-token", "/events/event-1", 200),
    ("buyer-token", "/account", 200),
    ("buyer-token", "/checkout/hold-1", 200),
    ("buyer-token", "/orders", 200),
    ("buyer-token", "/orders/order-9?confirmed=1", 200),
    ("buyer-token", "/admin/rates", 403),
    ("admin-token", "/admin/rates", 200),
    ("admin-token", "/admin/audit", 200),
]


@pytest.mark.requirement("system-027")
@pytest.mark.parametrize(("token", "path", "status"), PAGES)
def test_no_english_is_left_on_any_page_when_spanish(token, path, status):
    client, _ = make_client("es")
    if token:
        login_as(client, token)
    response = client.get(path, headers=ENGLISH_BROWSER)
    assert response.status_code == status
    page = response.get_data(as_text=True)
    assert '<html lang="es">' in page
    assert english_left(page) == []


@pytest.mark.requirement("system-027")
@pytest.mark.parametrize(("token", "path", "status"), PAGES)
def test_the_same_pages_in_english_still_show_english(token, path, status):
    """The check above is not vacuous: in English the same pages show catalog English."""
    client, _ = make_client("en")
    if token:
        login_as(client, token)
    response = client.get(path, headers=SPANISH_BROWSER)
    assert response.status_code == status
    assert english_left(response.get_data(as_text=True)) != []


@pytest.mark.requirement("system-027")
def test_page_titles_and_error_pages_are_spanish():
    client, _ = make_client("es")
    assert "<title>Iniciar sesión · EventHub</title>" in client.get("/login").get_data(as_text=True)
    missing = client.get("/no-such-page").get_data(as_text=True)
    assert "No pudimos completar la solicitud" in missing and "No encontramos esa página." in missing
    login_as(client, "buyer-token")
    forbidden = client.get("/admin/audit").get_data(as_text=True)
    assert "Solo para administradores." in forbidden
    assert 'data-error-code="forbidden"' in forbidden  # codes stay codes
    login_as(client, "admin-token")
    assert "<title>Registro de auditoría · Administración · EventHub</title>" in client.get(
        "/admin/audit"
    ).get_data(as_text=True)


# --------------------------------------- system-027: messages the web layer writes


@pytest.mark.requirement("system-027", "purchase-017")
@pytest.mark.parametrize("outcome", sorted(set(OUTCOME_ERRORS) - {"cancelled", "not_enough_tickets"}))
def test_every_purchase_rejection_is_spanish_and_keeps_its_code(outcome):
    client, services = make_client("es")
    services.checkout.start_outcome = outcome
    token = login_as(client)
    response = client.post(
        "/events/event-1/checkout", data={"csrf_token": token, "quantity": "2", "currency": "EUR"}
    )
    body = response.get_data(as_text=True)
    key, status = OUTCOME_ERRORS[outcome]
    assert response.status_code == status
    assert html_lib.escape(CATALOGS["es"][key], quote=False) in body
    assert f'data-error-code="{outcome}"' in body


@pytest.mark.requirement("system-027", "purchase-017")
@pytest.mark.parametrize(
    ("available", "english", "spanish"),
    [
        (1, "Only 1 ticket left for this event. Choose 1 or fewer.", "Solo queda 1 entrada para este evento. Elige 1 o menos."),
        (3, "Only 3 tickets left for this event. Choose 3 or fewer.", "Solo quedan 3 entradas para este evento. Elige 3 o menos."),
        (None, "Sorry, there are not enough tickets left for that quantity.", "Lo sentimos, no quedan suficientes entradas para esa cantidad."),
    ],
)  # fmt: skip
def test_not_enough_tickets_in_both_languages(available, english, spanish):
    for language, expected in (("en", english), ("es", spanish)):
        client, services = make_client(language)
        services.checkout.start_outcome = "not_enough_tickets"
        services.checkout.available = available
        token = login_as(client)
        body = client.post(
            "/events/event-1/checkout", data={"csrf_token": token, "quantity": "4", "currency": "EUR"}
        ).get_data(as_text=True)
        assert expected in body, language


@pytest.mark.requirement("system-027")
def test_flash_messages_are_spanish():
    client, services = make_client("es")
    token = login_as(client)
    client.post("/logout", data={"csrf_token": token})
    assert "Cerraste sesión." in client.get("/events").get_data(as_text=True)

    client.get("/register")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    client.post(
        "/register", data={"csrf_token": token, "name": "Ana", "email": "ana@usf.edu", "password": "x" * 8}
    )
    assert "Cuenta creada. Inicia sesión." in client.get("/login").get_data(as_text=True)

    anonymous = client.post("/events/event-1/checkout", data={"csrf_token": token, "quantity": "1"})
    assert anonymous.status_code == 302
    assert "Inicia sesión para comprar entradas." in client.get(anonymous.location).get_data(as_text=True)

    token = login_as(client, "admin-token")
    client.post("/admin/rates", data={"csrf_token": token, "currency": "EUR", "rate": "0.95"})
    assert "Tipo de cambio de EUR guardado." in client.get("/admin/rates").get_data(as_text=True)


@pytest.mark.requirement("system-027")
def test_expired_form_message_is_spanish():
    client, _ = make_client("es")
    login_as(client)
    response = client.post("/logout", data={})
    assert response.status_code == 400
    assert "Tu formulario expiró. Vuelve a cargar la página e inténtalo de nuevo." in response.get_data(
        as_text=True
    )


@pytest.mark.requirement("system-027", "identity-004")
def test_service_errors_with_a_fixed_sentence_are_shown_in_spanish():
    client, _ = make_client("es")
    client.get("/login")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    failed = client.post("/login", data={"csrf_token": token, "email": "a@b.co", "password": "nope"})
    assert failed.status_code == 401
    assert "Correo o contraseña no válidos." in failed.get_data(as_text=True)

    token = login_as(client)
    wrong = client.post(
        "/account/email", data={"csrf_token": token, "new_email": "x@y.co", "current_password": "no"}
    )
    assert "Tu contraseña actual no es correcta." in wrong.get_data(as_text=True)
    taken = client.post(
        "/account/email",
        data={"csrf_token": token, "new_email": "taken@example.com", "current_password": "right-password"},
    )
    assert "Ese correo ya lo usa otra cuenta." in taken.get_data(as_text=True)  # the email-change sentence
    currency = client.post("/account", data={"csrf_token": token, "currency": "XYZ"})
    assert "Esa moneda no está disponible." in currency.get_data(as_text=True)


@pytest.mark.requirement("system-027")
def test_input_dependent_service_sentences_stay_english_as_decided():
    """ADR-011 decision 6: invalid-rate / invalid-registration keep the service's sentence."""
    client, _ = make_client("es")
    token = login_as(client, "admin-token")
    bad = client.post("/admin/rates", data={"csrf_token": token, "currency": "EUR", "rate": "-1"})
    page = bad.get_data(as_text=True)
    assert "Rate must be greater than 0." in page
    assert "Tipos de cambio" in page  # the page around it is Spanish


# ------------------------------------------------- English is unchanged (characterization)

# The English sentences exactly as release 1.3.0 wrote them in app/web/__init__.py.
RELEASE_1_3_0_OUTCOMES = {
    "quantity_zero": "Choose at least 1 ticket.",
    "quantity_negative": "The number of tickets cannot be negative. Choose 1 or more.",
    "invalid_quantity": "Enter the number of tickets as a whole number, such as 2.",
    "unsupported_currency": "That currency is not supported. Choose one from the list.",
    "event_not_found": "We could not find that event.",
    "sold_out": "Sorry, this event is sold out.",
    "limit_exceeded": "That would go over the per-account ticket limit for this event.",
    "sales_closed": "Ticket sales have closed for this event because it has already started.",
    "rate_limited": "Too many purchase attempts from your account. Please wait a minute and try again.",
    "not_authenticated": "Please log in to buy tickets. You will come back to this event afterwards.",
    "eligibility_changed": (
        "The student discount no longer applies to your account (for example, because your email changed). "
        "The tickets were released and nothing was charged. Please start again to see the new price."
    ),
    "idempotency_key_required": "This form is out of date. Reload the page and try again.",
    "idempotency_conflict": "This form was already used for a different purchase. Reload the page and try again.",
    "hold_expired": "Your 10-minute hold expired and the tickets were released. Please start again.",
    "hold_not_found": "We could not find that checkout.",
    "hold_terminal": "This checkout is already finished.",
    "payment_failed": "The simulated payment was declined. Your tickets were released and no order was created.",
    "cancelled": "Checkout cancelled. The tickets were released.",
    "internal_error": "Something went wrong. Nothing was charged.",
}


@pytest.mark.requirement("system-027", "purchase-017")
def test_english_outcome_sentences_are_word_for_word_release_1_3_0():
    assert set(RELEASE_1_3_0_OUTCOMES) == set(OUTCOME_ERRORS) - {"not_enough_tickets"}
    for outcome, sentence in RELEASE_1_3_0_OUTCOMES.items():
        assert CATALOGS["en"][OUTCOME_ERRORS[outcome][0]] == sentence, outcome


@pytest.mark.requirement("system-027")
def test_english_flash_messages_are_unchanged():
    client, _ = make_client(None)
    token = login_as(client)
    client.post("/account", data={"csrf_token": token, "currency": "USD"})
    assert "Saved. This currency is now preselected at checkout and used for Quick Buy." in client.get(
        "/account"
    ).get_data(as_text=True)
    client.post("/logout", data={"csrf_token": token})
    assert "You have been logged out." in client.get("/events").get_data(as_text=True)
    token = login_as(client, "admin-token")
    client.post("/admin/rates", data={"csrf_token": token, "currency": "EUR", "rate": "0.95"})
    assert "Exchange rate for EUR saved." in client.get("/admin/rates").get_data(as_text=True)


def _service_sentences() -> dict[str, set[str]]:
    """code -> sentences, from every ServiceError(code, "sentence", ...) the services raise."""
    found: dict[str, set[str]] = {}
    for name in ("app/wiring.py", "app/web/services.py"):
        for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "ServiceError"
                and len(node.args) >= 2
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args[:2])
            ):
                found.setdefault(node.args[0].value, set()).add(node.args[1].value)
    return found


@pytest.mark.requirement("system-027")
def test_english_text_shown_by_code_is_the_services_own_sentence():
    """If a service's sentence is edited, this fails until the English catalog is edited too."""
    sentences = _service_sentences()
    for code, key in {**SERVICE_ERROR_KEYS, "email-taken (email change)": "error_email_taken_change"}.items():
        code = code.split(" ")[0]
        assert CATALOGS["en"][key] in sentences[code], (code, key)
        assert not placeholders(CATALOGS["en"][key])
