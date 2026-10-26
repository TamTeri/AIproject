"""Buyer and administrator web pages (server-rendered HTML).

Routes only translate HTTP <-> service ports. They never compute prices,
check inventory or write audit rows; those live in the feature packages.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from datetime import datetime
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

from app.pricing.calculator import format_rate

from .services import ServiceError, WebServices, default_services

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

web = Blueprint("web", __name__, static_folder="static", static_url_path="/assets")

SESSION_TOKEN_KEY = "session_token"
CSRF_KEY = "csrf_token"

OUTCOME_MESSAGES: dict[str, tuple[str, int]] = {
    "invalid_quantity": ("Choose a whole number of tickets, at least 1.", 400),
    "unsupported_currency": ("That currency is not supported. Choose one from the list.", 400),
    "event_not_found": ("We could not find that event.", 404),
    "sold_out": ("Sorry, there are not enough tickets left for that quantity.", 409),
    "limit_exceeded": ("That would go over the per-account ticket limit for this event.", 409),
    "hold_expired": (
        "Your 10-minute hold expired and the tickets were released. Please start again.",
        409,
    ),
    "hold_not_found": ("We could not find that checkout.", 404),
    "hold_terminal": ("This checkout is already finished.", 409),
    "payment_failed": (
        "The simulated payment was declined. Your tickets were released and no order was created.",
        402,
    ),
    "cancelled": ("Checkout cancelled. The tickets were released.", 200),
    "internal_error": ("Something went wrong. Nothing was charged.", 500),
}


# --------------------------------------------------------------------- setup


def register_web(app: Flask, services: WebServices | Any | None = None) -> Flask:
    """Attach the web boundary to an existing Flask application."""
    if "web" not in app.blueprints:
        app.register_blueprint(web)
    app.extensions["eventhub_web_services"] = services or default_services()
    existing_loader = app.jinja_loader
    loaders = [FileSystemLoader(str(_TEMPLATES))]
    if existing_loader:
        loaders.append(existing_loader)
    app.jinja_loader = ChoiceLoader(loaders)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.filters["rate"] = format_rate
    app.jinja_env.filters["when"] = format_when
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
    """Readable dates: "Sun, Nov 1, 2026 · 7:00 PM" (time only with style="time")."""
    if not isinstance(value, datetime):
        return "" if value is None else str(value)
    time_text = value.strftime("%I:%M %p").lstrip("0")
    if style == "time":
        return time_text
    return f"{value.strftime('%a, %b')} {value.day}, {value.year} · {time_text}"


def _services() -> Any:
    return current_app.extensions["eventhub_web_services"]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


# ------------------------------------------------------- session / security


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
            abort(400, description="Your form expired. Reload the page and try again.")


@web.after_app_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "frame-ancestors 'none'; form-action 'self'",
    )
    return response


@web.app_errorhandler(400)
def _bad_request(error):
    return _error_page(ServiceError("bad-request", getattr(error, "description", "Bad request."), 400))


@web.app_errorhandler(403)
def _forbidden(_error):
    return _error_page(ServiceError("forbidden", "Administrators only.", 403))


@web.app_errorhandler(404)
def _not_found(_error):
    return _error_page(ServiceError("not-found", "We could not find that page.", 404))


def _error_page(error: ServiceError):
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


def _outcome_error(outcome: str) -> ServiceError:
    message, status = OUTCOME_MESSAGES.get(outcome, ("We could not complete that purchase.", 400))
    return ServiceError(outcome, message, status)


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
        return _error_page(ServiceError("event-not-found", "We could not find that event.", 404))
    try:
        currencies = _services().pricing.currencies()
        price = _services().pricing.base_price_display(base_price_minor=_field(event, "base_price_minor", 0))
    except ServiceError:
        currencies, price = [], None
    principal = _principal()
    preferred = _field(principal, "preferred_currency") or "USD"
    body = render_template(
        "event_detail.html",
        event=event,
        currencies=currencies,
        price=price,
        preferred_currency=(form or {}).get("currency") or preferred,
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
            render_template("login.html", next_target=safe_next, error=error.message, email=email),
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
    flash("You have been logged out.")
    return redirect(url_for("web.events"))


@web.get("/register")
def register():
    return render_template("register.html", form={})


@web.post("/register")
def register_submit():
    name = request.form.get("name", "")
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    try:
        _services().identity.register(name=name, email=email, password=password)
    except ServiceError as error:
        return (
            render_template("register.html", error=error.message, form={"name": name, "email": email}),
            error.status_code,
        )
    flash("Account created. Please log in.")
    return redirect(url_for("web.login"))


@web.route("/account", methods=["GET", "POST"])
def account():
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    error = None
    if request.method == "POST":
        try:
            _services().identity.set_preferred_currency(
                account_id=_buyer_id(), currency=request.form.get("currency", "")
            )
            flash("Saved. Quick Buy will use this currency.")
            return redirect(url_for("web.account"))
        except ServiceError as service_error:
            error = service_error
    try:
        currencies = _services().pricing.currencies()
    except ServiceError:
        currencies = []
    return (
        render_template("account.html", currencies=currencies, error=error),
        error.status_code if error else 200,
    )


# ----------------------------------------------------------------- purchase


@web.post("/events/<event_id>/checkout")
def checkout_start(event_id: str):
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    quantity = request.form.get("quantity", "")
    currency = request.form.get("currency", "")
    try:
        result = _services().checkout.start(
            buyer_id=_buyer_id(), event_id=event_id, quantity=quantity, currency=currency
        )
    except ServiceError as error:
        return _error_page(error)
    outcome = _outcome_value(result)
    if outcome == "hold_created":
        hold_id = _field(_field(result, "hold"), "id")
        return redirect(url_for("web.checkout_review", hold_id=hold_id))
    return event_detail(
        event_id, error=_outcome_error(outcome), form={"quantity": quantity, "currency": currency}
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
        return redirect(url_for("web.login", next=url_for("web.checkout_review", hold_id=hold_id)))
    try:
        result = _services().checkout.pay(
            buyer_id=_buyer_id(), hold_id=hold_id, payment_choice=request.form.get("payment", "approve")
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
        flash(OUTCOME_MESSAGES["cancelled"][0])
        return redirect(url_for("web.events"))
    return _error_page(_outcome_error(outcome))


@web.post("/events/<event_id>/quick-buy")
def quick_buy(event_id: str):
    """catalog-008 / purchase-011: double-click (or the Quick Buy button)
    buys one ticket in the saved currency through the same purchase path."""
    if _principal() is None:
        return redirect(url_for("web.login", next=_login_target()))
    try:
        result = _services().purchase.quick_buy(
            buyer_id=_buyer_id(),
            event_id=event_id,
            currency=_field(_principal(), "preferred_currency"),
        )
    except ServiceError as error:
        return _error_page(error)
    return _purchase_response(result)


def _purchase_response(result: Any):
    outcome = _outcome_value(result)
    if outcome == "success":
        order_id = _field(_field(result, "order"), "id")
        return redirect(url_for("web.order_detail", order_id=order_id, confirmed=1))
    return _error_page(_outcome_error(outcome))


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
        return _error_page(ServiceError("order-not-found", "We could not find that order.", 404))
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
        _services().admin.set_rate(actor=_principal(), currency=currency, rate=request.form.get("rate", ""))
    except ServiceError as error:
        if error.status_code == 403:
            return _error_page(error)
        return admin_rates(error=error)
    flash(f"Exchange rate for {currency.upper()} saved.")
    return redirect(url_for("web.admin_rates"))


@web.get("/admin/audit")
@admin_required
def admin_audit():
    try:
        page = _services().admin.audit_page(actor=_principal(), before_id=request.args.get("before"))
    except ServiceError as error:
        return _error_page(error)
    return render_template("admin_audit.html", page=page)


__all__ = ["OUTCOME_MESSAGES", "create_web_app", "register_web", "web"]
