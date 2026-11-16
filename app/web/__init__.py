"""Buyer and administrator web pages (server-rendered HTML).

Routes only translate HTTP <-> service ports. They never compute prices,
check inventory or write audit rows; those live in the feature packages.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jinja2 import ChoiceLoader, FileSystemLoader

from app.i18n import DEFAULT_LOCALE, configured_locale, format_money_text, resolve_locale, translate
from app.i18n import format_when as _format_when
from app.i18n.locales import COOKIE_NAME, LANGUAGE_NAMES, SUPPORTED, match_tag
from app.pricing.calculator import format_rate

from .services import ServiceError, WebServices, default_services

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

web = Blueprint("web", __name__, static_folder="static", static_url_path="/assets")

SESSION_TOKEN_KEY = "session_token"
CSRF_KEY = "csrf_token"

# purchase-017 (Call 5): every rejection has its own message.
# outcome -> (message key in app/i18n/<lang>.json, HTTP status). The sentences live in the
# catalogs (system-027, ADR-011): en.json holds the English, word for word as before.
OUTCOME_ERRORS: dict[str, tuple[str, int]] = {
    "quantity_zero": ("outcome_quantity_zero", 400),
    "quantity_negative": ("outcome_quantity_negative", 400),
    "invalid_quantity": ("outcome_invalid_quantity", 400),
    "unsupported_currency": ("outcome_unsupported_currency", 400),
    "event_not_found": ("outcome_event_not_found", 404),
    "sold_out": ("outcome_sold_out", 409),
    # one/other/unknown variants are chosen from the result (see _outcome_error).
    "not_enough_tickets": ("outcome_not_enough_tickets_other", 409),
    "limit_exceeded": ("outcome_limit_exceeded", 409),
    "sales_closed": ("outcome_sales_closed", 409),
    "rate_limited": ("outcome_rate_limited", 429),
    "not_authenticated": ("outcome_not_authenticated", 401),
    "eligibility_changed": ("outcome_eligibility_changed", 409),
    "idempotency_key_required": ("outcome_idempotency_key_required", 400),
    "idempotency_conflict": ("outcome_idempotency_conflict", 409),
    "hold_expired": ("outcome_hold_expired", 409),
    "hold_not_found": ("outcome_hold_not_found", 404),
    "hold_terminal": ("outcome_hold_terminal", 409),
    "payment_failed": ("outcome_payment_failed", 402),
    "cancelled": ("outcome_cancelled", 200),
    "internal_error": ("outcome_internal_error", 500),
}

# system-027, ADR-011 decision 6: service errors whose code always carries the same sentence are shown
# from the catalog, so they follow the page language. Codes whose sentence is built from the
# input (invalid-registration, invalid-email, invalid-rate) keep the service's English.
SERVICE_ERROR_KEYS: dict[str, str] = {
    "invalid-credentials": "error_invalid_credentials",
    "wrong-password": "error_wrong_password",
    "unsupported-currency": "error_unsupported_currency",
    "email-taken": "error_email_taken",
    "forbidden": "error_forbidden",
    "service-unavailable": "error_service_unavailable",
}

# purchase-016: at most one audit record per browser session in this many seconds for
# purchases from people who are not logged in, so a script cannot flood the audit log.
ANONYMOUS_AUDIT_SECONDS = 10
# identity-014: wrong current passwords on the email-change form before the session ends.
EMAIL_CHANGE_MAX_FAILURES = 5


# --------------------------------------------------------------------- setup


def register_web(app: Flask, services: WebServices | Any | None = None) -> Flask:
    """Attach the web boundary to an existing Flask application."""
    if "web" not in app.blueprints:
        app.register_blueprint(web)
    # system-025: create_app() has already checked this through Settings; apps built without
    # Settings (create_web_app) are checked here, so no path carries an unchecked value.
    app.config["EVENTHUB_LANGUAGE"] = configured_locale(app.config.get("EVENTHUB_LANGUAGE"))
    app.extensions["eventhub_web_services"] = services or default_services()
    existing_loader = app.jinja_loader
    loaders = [FileSystemLoader(str(_TEMPLATES))]
    if existing_loader:
        loaders.append(existing_loader)
    app.jinja_loader = ChoiceLoader(loaders)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["idempotency_key"] = new_idempotency_key
    app.jinja_env.filters["rate"] = format_rate
    app.jinja_env.filters["when"] = lambda value, style="datetime": _format_when(
        value, g.get("locale", "en"), style
    )
    app.jinja_env.filters["money"] = lambda value: format_money_text(value, g.get("locale", "en"))
    app.jinja_env.globals["_"] = lambda key, **values: translate(key, g.get("locale", "en"), **values)
    app.jinja_env.globals["locale"] = lambda: g.get("locale", "en")
    app.jinja_env.globals["languages"] = [(code, LANGUAGE_NAMES[code]) for code in SUPPORTED]
    app.jinja_env.globals["current_user"] = lambda: g.get("principal")
    return app


def create_web_app(
    *,
    services: WebServices | Any | None = None,
    config: Mapping[str, Any] | None = None,
) -> Flask:
    """Create an isolated Flask web app for contract tests with fake services."""
    app = Flask(__name__)
    app.config.from_mapping(SECRET_KEY=secrets.token_hex(16), TESTING=False)
    if config:
        app.config.update(config)
    register_web(app, services)
    return app


def format_when(value: Any, style: str = "datetime") -> str:
    """English dates ("Sun, Nov 1, 2026 · 7:00 PM"); pages use the locale-aware |when filter."""
    return _format_when(value, "en", style)


@web.before_app_request
def _resolve_locale() -> None:
    """system-020/024: ?lang= > cookie > EVENTHUB_LANGUAGE > Accept-Language > en, all allowlisted."""
    g.locale = resolve_locale(
        request.args.get("lang"),
        request.cookies.get(COOKIE_NAME),
        request.headers.get("Accept-Language"),
        configured=current_app.config.get("EVENTHUB_LANGUAGE"),
    )
    # Remember an explicit choice. The cookie value is the allowlisted code, never the input.
    g.remember_locale = match_tag(request.args.get("lang"))


def _t(key: str, **values: Any) -> str:
    """system-027: a sentence the web layer writes, in the page's language."""
    return translate(key, g.get("locale", DEFAULT_LOCALE), **values)


def _localized(error: ServiceError, overrides: Mapping[str, str] | None = None) -> ServiceError:
    """Show a service error in the page language when its code has a fixed sentence (ADR-011).

    ``overrides`` picks a different key for a code on one page (the two "email-taken" sentences).
    """
    key = (overrides or {}).get(error.code) or SERVICE_ERROR_KEYS.get(error.code)
    if key is None:
        return error
    return ServiceError(error.code, _t(key), error.status_code, error.fields)


def _services() -> Any:
    return current_app.extensions["eventhub_web_services"]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


# ------------------------------------------------------- session / security


def new_idempotency_key() -> str:
    """purchase-014: a fresh one-time key for each purchase form shown."""
    return secrets.token_urlsafe(24)


def csrf_token() -> str:
    token = session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_KEY] = token
    return token


@web.before_app_request
def _load_principal_and_check_csrf() -> None:
    g.principal = None
    token = session.get(SESSION_TOKEN_KEY)
    if token:
        try:
            g.principal = _services().identity.resolve_session(token=token)
        except ServiceError:
            g.principal = None
        if g.principal is None:
            session.pop(SESSION_TOKEN_KEY, None)
            session["session_expired"] = True  # shown once on the login page

    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not current_app.config.get(
        "EVENTHUB_CSRF_DISABLED"
    ):
        expected = session.get(CSRF_KEY)
        supplied = request.form.get(CSRF_KEY, "")
        if not expected or not secrets.compare_digest(str(expected), str(supplied)):
            abort(400, description=_t("error_form_expired"))


@web.after_app_request
def _security_headers(response):
    if g.get("remember_locale"):
        response.set_cookie(COOKIE_NAME, g.remember_locale, max_age=31536000, samesite="Lax", httponly=True)
    response.vary.add("Accept-Language")
    response.vary.add("Cookie")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if response.mimetype == "text/html":
        # Pages hold one-time purchase keys and personal data: never reuse a
        # stored copy, so Back shows a fresh form (purchase-014).
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "frame-ancestors 'none'; form-action 'self'",
    )
    return response


@web.app_errorhandler(400)
def _bad_request(error):
    description = getattr(error, "description", None) or _t("error_bad_request")
    return _error_page(ServiceError("bad-request", description, 400))


@web.app_errorhandler(403)
def _forbidden(_error):
    return _error_page(ServiceError("forbidden", _t("error_forbidden"), 403))


@web.app_errorhandler(404)
def _not_found(_error):
    return _error_page(ServiceError("not-found", _t("error_page_not_found"), 404))


def _error_page(error: ServiceError):
    error = _localized(error)
    return render_template("error.html", error=error), error.status_code


def _is_safe_relative_target(target: str | None) -> bool:
    """Only a same-origin relative path is an allowed login return target."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    return "\\" not in target and "\n" not in target and "\r" not in target


def _principal() -> Any:
    return g.get("principal")


def _buyer_id() -> str | None:
    principal = _principal()
    return str(_field(principal, "account_id")) if principal is not None else None


def admin_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """admin-002 / identity-011: buyers can never reach admin functions."""

    def wrapped(*args: Any, **kwargs: Any):
        principal = _principal()
        if principal is None:
            return redirect(url_for("web.login", next=request.path))
        if not _field(principal, "is_admin", False):
            abort(403)
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def _post_return_path() -> str:
    """For a POST that needs login, send the buyer back to the matching page."""
    event_id = (request.view_args or {}).get("event_id")
    if event_id is not None:
        return url_for("web.event_detail", event_id=event_id)
    return url_for("web.events")


def _login_target() -> str:
    """identity-008: where to return after login (a GET-able page)."""
    return request.path if request.method == "GET" else _post_return_path()


def _outcome_value(result: Any) -> str:
    return str(_field(result, "outcome", ""))


def _outcome_error(outcome: str, result: Any = None) -> ServiceError:
    key, status = OUTCOME_ERRORS.get(outcome, ("outcome_unknown", 400))
    values: dict[str, Any] = {}
    if outcome == "not_enough_tickets":
        left = _field(result, "available")
        if isinstance(left, int) and left > 0:
            key = "outcome_not_enough_tickets_one" if left == 1 else "outcome_not_enough_tickets_other"
            values = {"count": left}
        else:
            key = "outcome_not_enough_tickets_unknown"
    return ServiceError(outcome, _t(key, **values), status)


def _not_logged_in_purchase(event_id: str | None, *, next_path: str):
    """purchase-016: record the attempt, explain why, and send the person to log in.

    Recording is best effort: the redirect to login must work even if the
    database is unavailable, and one browser session is recorded at most once
    every ANONYMOUS_AUDIT_SECONDS.
    """
    now = time.time()
    if now - float(session.get("anonymous_attempt_logged_at", 0)) >= ANONYMOUS_AUDIT_SECONDS:
        session["anonymous_attempt_logged_at"] = now
        try:
            _services().checkout.record_unauthenticated(
                event_id=event_id,
                quantity=request.form.get("quantity"),
                currency=request.form.get("currency"),
            )
        except Exception:  # never turn "please log in" into an error page
            current_app.logger.warning("could not record a not-logged-in purchase attempt", exc_info=True)
    flash(_t("outcome_not_authenticated"))
    return redirect(url_for("web.login", next=next_path))


# ------------------------------------------------------------------ catalog


@web.get("/")
def home():
    return redirect(url_for("web.events"))


@web.get("/events")
def events():
    query = request.args.get("q", "").strip() or None
    try:
        result = _services().catalog.list_events(query=query)
    except ServiceError as error:
        return _error_page(error)
    event_list = _field(result, "events", []) or []
    no_match = bool(_field(result, "no_match", False))
    return render_template("events.html", events=event_list, query=query, no_match=no_match)


@web.get("/events/<event_id>")
def event_detail(event_id: str, *, error: ServiceError | None = None, form: dict | None = None):
    try:
        event = _services().catalog.get_event(event_id=event_id)
    except ServiceError as service_error:
        return _error_page(service_error)
    if event is None:
        return _error_page(ServiceError("event-not-found", _t("outcome_event_not_found"), 404))
    try:
        currencies = _services().pricing.currencies()
        price = _services().pricing.base_price_display(base_price_minor=_field(event, "base_price_minor", 0))
    except ServiceError:
        currencies, price = [], None
    principal = _principal()
    saved_currency = _field(principal, "preferred_currency") or "USD"
    body = render_template(
        "event_detail.html",
        event=event,
        currencies=currencies,
        price=price,
        preferred_currency=(form or {}).get("currency") or saved_currency,
        saved_currency=saved_currency,
        quantity=(form or {}).get("quantity", "1"),
        error=error,
    )
    return body, (error.status_code if error else 200)


# ----------------------------------------------------------------- identity


@web.get("/login")
def login():
    next_target = request.args.get("next")
    return render_template(
        "login.html",
        next_target=next_target if _is_safe_relative_target(next_target) else None,
        expired=bool(session.pop("session_expired", False)),
    )


@web.post("/login")
def login_submit():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    next_target = request.form.get("next")
    safe_next = next_target if _is_safe_relative_target(next_target) else None
    try:
        principal = _services().identity.authenticate(email=email, password=password)
        token = _services().identity.start_session(account_id=str(_field(principal, "account_id")))
    except ServiceError as error:
        return (
            render_template(
                "login.html", next_target=safe_next, error=_localized(error).message, email=email
            ),
            error.status_code,
        )
    session.clear()  # fresh session contents on login
    session[SESSION_TOKEN_KEY] = token
    session.permanent = False
    return redirect(safe_next or url_for("web.events"))


@web.post("/logout")
def logout():
    _services().identity.end_session(token=session.get(SESSION_TOKEN_KEY))
    session.clear()
    flash(_t("flash_logged_out"))
    return redirect(url_for("web.events"))


def _currencies() -> list[str]:
    try:
        return list(_services().pricing.currencies())
    except ServiceError:
        return []


@web.get("/register")
def register():
    return render_template("register.html", form={}, currencies=_currencies())


@web.post("/register")
def register_submit():
    name = request.form.get("name", "")
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    currency = request.form.get("currency") or None
    try:
        _services().identity.register(name=name, email=email, password=password, currency=currency)
    except ServiceError as error:
        return (
            render_template(
                "register.html",
                error=_localized(error).message,
                form={"name": name, "email": email, "currency": currency},
                currencies=_currencies(),
            ),
            error.status_code,
        )
    flash(_t("flash_account_created"))
    return redirect(url_for("web.login"))


def _account_page(*, error: ServiceError | None = None, email_error: ServiceError | None = None):
    try:
        discount = bool(_services().pricing.student_discount_applies(email=_field(_principal(), "email")))
    except (ServiceError, AttributeError):
        discount = None
    failed = error or email_error
    return (
        render_template(
            "account.html",
            currencies=_currencies(),
            error=error,
            email_error=email_error,
            discount=discount,
        ),
        failed.status_code if failed else 200,
    )


@web.route("/account", methods=["GET", "POST"])
def account():
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    if request.method == "POST":
        try:
            _services().identity.set_preferred_currency(
                account_id=_buyer_id(), currency=request.form.get("currency", "")
            )
            flash(_t("flash_currency_saved"))
            return redirect(url_for("web.account"))
        except ServiceError as service_error:
            return _account_page(error=_localized(service_error))
    return _account_page()


@web.post("/account/email")
def account_email():
    """identity-014 (Call 5): change the login email; discounts follow it (pricing-011)."""
    if _principal() is None:
        return redirect(url_for("web.login", next=url_for("web.account")))
    try:
        _services().identity.change_email(
            account_id=_buyer_id(),
            new_email=request.form.get("new_email", ""),
            current_password=request.form.get("current_password", ""),
        )
    except ServiceError as error:
        if error.code == "wrong-password":
            # A stolen session must not be usable to guess the password.
            failures = int(session.get("email_change_failures", 0)) + 1
            session["email_change_failures"] = failures
            if failures >= EMAIL_CHANGE_MAX_FAILURES:
                _services().identity.end_session(token=session.get(SESSION_TOKEN_KEY))
                session.clear()
                flash(_t("flash_email_change_locked"))
                return redirect(url_for("web.login"))
        return _account_page(email_error=_localized(error, {"email-taken": "error_email_taken_change"}))
    session.pop("email_change_failures", None)
    flash(_t("flash_email_changed"))
    return redirect(url_for("web.account"))


# ----------------------------------------------------------------- purchase


@web.post("/events/<event_id>/checkout")
def checkout_start(event_id: str):
    if _principal() is None:
        return _not_logged_in_purchase(event_id, next_path=_login_target())
    quantity = request.form.get("quantity", "")
    currency = request.form.get("currency", "")
    try:
        result = _services().checkout.start(
            buyer_id=_buyer_id(),
            event_id=event_id,
            quantity=quantity,
            currency=currency,
            idempotency_key=request.form.get("idempotency_key"),
        )
    except ServiceError as error:
        return _error_page(error)
    outcome = _outcome_value(result)
    if outcome == "hold_created":
        hold_id = _field(_field(result, "hold"), "id")
        return redirect(url_for("web.checkout_review", hold_id=hold_id))
    return event_detail(
        event_id, error=_outcome_error(outcome, result), form={"quantity": quantity, "currency": currency}
    )


@web.get("/checkout/<hold_id>")
def checkout_review(hold_id: str):
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    try:
        hold = _services().checkout.review(buyer_id=_buyer_id(), hold_id=hold_id)
    except ServiceError as error:
        return _error_page(error)
    if hold is None:
        return _error_page(_outcome_error("hold_not_found"))
    if str(_field(hold, "status")) != "active":
        return _error_page(_outcome_error("hold_terminal"))
    return render_template("checkout.html", hold=hold)


@web.post("/checkout/<hold_id>/pay")
def checkout_pay(hold_id: str):
    if _principal() is None:
        return _not_logged_in_purchase(None, next_path=url_for("web.checkout_review", hold_id=hold_id))
    try:
        result = _services().checkout.pay(
            buyer_id=_buyer_id(),
            hold_id=hold_id,
            payment_choice=request.form.get("payment", "approve"),
            idempotency_key=request.form.get("idempotency_key"),
        )
    except ServiceError as error:
        return _error_page(error)
    return _purchase_response(result)


@web.post("/checkout/<hold_id>/cancel")
def checkout_cancel(hold_id: str):
    if _principal() is None:
        return redirect(url_for("web.login"))
    try:
        result = _services().checkout.cancel(buyer_id=_buyer_id(), hold_id=hold_id)
    except ServiceError as error:
        return _error_page(error)
    outcome = _outcome_value(result)
    if outcome == "cancelled":
        flash(_t("outcome_cancelled"))
        return redirect(url_for("web.events"))
    return _error_page(_outcome_error(outcome))


@web.post("/events/<event_id>/quick-buy")
def quick_buy(event_id: str):
    """catalog-008 / purchase-011: double-click (or the Quick Buy button)
    buys one ticket in the saved currency through the same purchase path."""
    if _principal() is None:
        return _not_logged_in_purchase(event_id, next_path=_login_target())
    try:
        result = _services().purchase.quick_buy(
            buyer_id=_buyer_id(),
            event_id=event_id,
            currency=_field(_principal(), "preferred_currency"),
            idempotency_key=request.form.get("idempotency_key"),
        )
    except ServiceError as error:
        return _error_page(error)
    return _purchase_response(result)


def _purchase_response(result: Any):
    outcome = _outcome_value(result)
    if outcome == "success":
        if _field(result, "replayed", False):
            flash(_t("flash_replayed"))  # purchase-014: the repeat landed on the same order
        order_id = _field(_field(result, "order"), "id")
        return redirect(url_for("web.order_detail", order_id=order_id, confirmed=1))
    return _error_page(_outcome_error(outcome, result))


# ------------------------------------------------------------------- orders


@web.get("/orders")
def orders():
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    try:
        order_list = _services().orders.list_for_buyer(buyer_id=_buyer_id())
    except ServiceError as error:
        return _error_page(error)
    return render_template("orders.html", orders=order_list or [])


@web.get("/orders/<order_id>")
def order_detail(order_id: str):
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    try:
        order = _services().orders.get_for_buyer(buyer_id=_buyer_id(), order_id=order_id)
    except ServiceError as error:
        return _error_page(error)
    if order is None:
        return _error_page(ServiceError("order-not-found", _t("error_order_not_found"), 404))
    return render_template(
        "order_detail.html", order=order, just_confirmed=request.args.get("confirmed") == "1"
    )


# -------------------------------------------------------------------- admin


@web.get("/admin")
@admin_required
def admin_home():
    return redirect(url_for("web.admin_rates"))


@web.get("/admin/rates")
@admin_required
def admin_rates(error: ServiceError | None = None):
    try:
        rates = _services().admin.list_rates(actor=_principal())
    except ServiceError as service_error:
        return _error_page(service_error)
    return render_template("admin_rates.html", rates=rates, error=error), (
        error.status_code if error else 200
    )


@web.post("/admin/rates")
@admin_required
def admin_rates_update():
    currency = request.form.get("currency", "")
    try:
        _services().admin.set_rate(
            actor=_principal(),
            currency=currency,
            rate=request.form.get("rate", ""),
            confirm_large_change=request.form.get("confirm_large_change") == "1",
        )
    except ServiceError as error:
        if error.status_code == 403:
            return _error_page(error)
        return admin_rates(error=_localized(error))
    flash(_t("flash_rate_saved", currency=currency.strip().upper()[:3]))
    return redirect(url_for("web.admin_rates"))


@web.get("/admin/audit")
@admin_required
def admin_audit():
    try:
        page = _services().admin.audit_page(actor=_principal(), before_id=request.args.get("before"))
    except ServiceError as error:
        return _error_page(error)
    return render_template("admin_audit.html", page=page)


__all__ = ["OUTCOME_ERRORS", "SERVICE_ERROR_KEYS", "create_web_app", "register_web", "web"]
