"""Black-box system tests for Part 7: EventHub configured to run in English or Spanish.

Each test starts EventHub the way an operator deploys it, with EVENTHUB_LANGUAGE set
(system-024), on the same seeded database as the other system tests. The browser asks
for English unless a test says otherwise, so a Spanish page proves that the
configuration, not the browser, chose the language. Expected Spanish text comes from
the requirements and the Spanish catalog (app/i18n/es.json), not from reading the code.
"""

from __future__ import annotations

import re

import pytest

from tests.system.support import ADMIN_EMAIL, ADMIN_PASSWORD, PASSWORD, EventHub, unique_email

pytestmark = pytest.mark.system

SPANISH_DATE = re.compile(
    r"\b(lun|mar|mié|jue|vie|sáb|dom), \d{1,2} (ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic) \d{4}"
)


def _log_in(hub: EventHub, email: str, password: str = PASSWORD) -> None:
    """Log in by field ids and the form's button: the button label is not English here."""
    hub.go("/login")
    hub.type("#email", email)
    hub.type("#password", password)
    hub.submit_main_form()
    hub.wait().until(lambda _: not hub.path.startswith("/login") or hub.exists(".error"))


@pytest.mark.requirement("system-024", "system-026")
def test_st71_spanish_deployment_shows_the_top_level_menu_in_spanish(browser_factory, configured_site):
    """ST-71 EventHub started with EVENTHUB_LANGUAGE=es shows the top-level menu in Spanish, even to a browser that asks for English."""
    ui = browser_factory(site=configured_site("es"))  # the browser sends Accept-Language: en-US
    ui.go("/events")
    assert ui.page_language() == "es"
    assert ui.menu() == ["EventHub", "Eventos", "Historial de pedidos", "Iniciar sesión", "Registrarse"]
    assert ui.text("h1") == "Eventos"
    assert ui.text("#language-switcher").startswith("Idioma:")


@pytest.mark.requirement("system-026", "identity-002", "admin-002")
def test_st72_spanish_menu_for_a_logged_in_buyer_and_an_administrator(ui, browser_factory, configured_site):
    """ST-72 On the Spanish deployment a buyer's and an administrator's top-level menus are in Spanish, and the admin pages follow."""
    account = ui.register(name="Ana Estudiante")  # created on the English site: same database
    spanish = browser_factory(site=configured_site("es"))
    _log_in(spanish, account.email)
    assert spanish.menu() == [
        "EventHub", "Eventos", "Historial de pedidos", "Cuenta", "Cerrar sesión (Ana Estudiante)",
    ]  # fmt: skip

    admin = browser_factory(site=configured_site("es"))
    _log_in(admin, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert "Administración" in admin.menu()
    admin.go("/admin/rates")
    assert admin.text("h1") == "Tipos de cambio"
    assert [e.text for e in admin.find_all("thead th")] == [
        "Moneda",
        "Tipo",
        "Última actualización",
        "Actualizar",
    ]
    admin.go("/admin/audit")
    assert admin.text("h1") == "Registro de intentos de compra"
    assert "Resultado" in [e.text for e in admin.find_all("thead th")]


@pytest.mark.requirement("system-024", "system-020")
def test_st73_the_configuration_decides_not_the_browser(browser_factory, configured_site):
    """ST-73 A Spanish browser sees English on a deployment configured for English, and Spanish on one that is not configured."""
    english_site = browser_factory(site=configured_site("en"), accept_language="es-MX,es")
    english_site.go("/events")
    assert english_site.page_language() == "en"
    assert english_site.menu() == ["EventHub", "Events", "Order history", "Log in", "Register"]

    not_configured = browser_factory(accept_language="es-MX,es")  # the default server: Call 6 behaviour
    not_configured.go("/events")
    assert not_configured.page_language() == "es"
    assert not_configured.menu()[1] == "Eventos"


@pytest.mark.requirement("system-020", "system-024")
def test_st74_a_visitor_can_still_switch_the_spanish_deployment_to_english(browser_factory, configured_site):
    """ST-74 On the Spanish deployment the footer link switches one visitor to English, and the choice is remembered."""
    ui = browser_factory(site=configured_site("es"))
    ui.go("/events")
    assert ui.page_language() == "es"
    ui.click('#language-switcher a[hreflang="en"]')
    ui.wait().until(lambda _: ui.page_language() == "en")
    assert ui.menu() == ["EventHub", "Events", "Order history", "Log in", "Register"]
    ui.go("/login")  # no ?lang: the cookie carries the choice
    assert ui.page_language() == "en"
    assert ui.text("h1") == "Log in"


@pytest.mark.requirement("system-027", "system-021", "system-022", "pricing-003", "orders-003")
def test_st75_spanish_buyer_journey_from_registration_to_order_history(browser_factory, configured_site):
    """ST-75 On the Spanish deployment: register, log in, buy 2 tickets in EUR, and read the confirmation and history, all in Spanish."""
    ui = browser_factory(site=configured_site("es"))
    email = unique_email("ana", "usf.edu")

    ui.go("/register")
    assert ui.text("h1") == "Registrarse"
    ui.type("#name", "Ana Estudiante")
    ui.type("#email", email)
    ui.type("#password", PASSWORD)
    ui.submit_main_form()
    assert "Cuenta creada. Inicia sesión." in ui.flash()
    assert ui.text("h1") == "Iniciar sesión"

    _log_in(ui, email)
    ui.search("jazz")
    assert ui.card_titles() == ["Bulls Jazz Ensemble"]
    ui.card_for("Bulls Jazz Ensemble").find_element("css selector", "p.muted").click()
    event_path = ui.wait_for_path(r"^/events/\d+$")

    ui.go(event_path)
    ui.type("#quantity", "2")
    ui.choose("#currency", "EUR")
    ui.submit_with(ui.find('main form[action$="/checkout"] button[type=submit]'))
    ui.wait_for_path(r"^/checkout/\d+$")
    assert ui.text("h1") == "Pago"
    # 2 x 15.00 USD = 30.00; 10% student discount -> 27.00 USD; x 0.92 -> 24.84 EUR, written 24,84 EUR
    assert ui.text("dd.total") == "24,84 EUR"
    ui.choose("#payment", "approve")
    ui.submit_with(ui.find('main form[action$="/pay"] button[type=submit]'))

    ui.wait_for_path(r"^/orders/\d+\?confirmed=1$")
    assert ui.text("h1") == "Pedido confirmado"
    summary = ui.summary()
    assert summary["Cantidad"] == "2"
    assert summary["Moneda de pago"] == "EUR"
    assert ui.text("dd.total") == "24,84 EUR"

    rows = ui.order_rows()
    assert ui.text("h1") == "Historial de pedidos"
    assert any("24,84 EUR" in row and SPANISH_DATE.search(row) for row in rows), rows


@pytest.mark.requirement("system-027", "identity-004", "purchase-017")
def test_st76_errors_and_rejections_are_spanish_on_the_spanish_deployment(
    ui, browser_factory, configured_site, db
):
    """ST-76 On the Spanish deployment a failed log-in, a missing page and a purchase rejection are explained in Spanish."""
    spanish = browser_factory(site=configured_site("es"))
    _log_in(spanish, "nobody@example.com", "wrong-password-1")
    assert spanish.error() == "Correo o contraseña no válidos."

    spanish.go("/no-such-page")
    assert spanish.text("h1") == "No pudimos completar la solicitud"
    assert spanish.text(".error p") == "No encontramos esa página."

    account = ui.register()
    event_id = db.create_event(capacity=1)
    _log_in(spanish, account.email)
    spanish.go(f"/events/{event_id}")
    spanish.type("#quantity", "3")
    spanish.submit_with(spanish.find('main form[action$="/checkout"] button[type=submit]'))
    assert spanish.error() == "Solo queda 1 entrada para este evento. Elige 1 o menos."
    assert spanish.error_code() == "not_enough_tickets"  # codes stay codes
