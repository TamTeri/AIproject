"""Buyer and administrator web pages (server-rendered HTML).

Routes only translate HTTP <-> service ports. They never compute prices,
check inventory or write audit rows; those live in the feature packages.
"""

from __future__ import annotations

import secrets
import time
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

# purchase-017 (Call 5): every rejection has its own message.
OUTCOME_MESSAGES: dict[str, tuple[str, int]] = {
    "quantity_zero": ("Choose at least 1 ticket.", 400),
    "quantity_negative": ("The number of tickets cannot be negative. Choose 1 or more.", 400),
    "invalid_quantity": ("Enter the number of tickets as a whole number, such as 2.", 400),
    "unsupported_currency": ("That currency is not supported. Choose one from the list.", 400),
    "event_not_found": ("We could not find that event.", 404),
    "sold_out": ("Sorry, this event is sold out.", 409),
    # {available} is filled in from the result (see _outcome_error).
    "not_enough_tickets": ("Only {available} left for this event. Choose {count} or fewer.", 409),
    "limit_exceeded": ("That would go over the per-account ticket limit for this event.", 409),
    "sales_closed": ("Ticket sales have closed for this event because it has already started.", 409),
    "rate_limited": (
        "Too many purchase attempts from your account. Please wait a minute and try again.",
        429,
    ),
    "not_authenticated": ("Please log in to buy tickets. You will come back to this event afterwards.", 401),
    "eligibility_changed": (
        "The student discount no longer applies to your account (for example, because your email "
        "changed). The tickets were released and nothing was charged. Please start again to see the "
        "new price.",
        409,
    ),
    "idempotency_key_required": ("This form is out of date. Reload the page and try again.", 400),
    "idempotency_conflict": (
        "This form was already used for a different purchase. Reload the page and try again.",
        409,
    ),
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

REPLAYED_MESSAGE = "You submitted this purchase more than once. We processed it only once."

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
    app.extensions["eventhub_web_services"] = services or default_services()
    existing_loader = app.jinja_loader
    loaders = [FileSystemLoader(str(_TEMPLATES))]
    if existing_loader:
        loaders.append(existing_loader)
    app.jinja_loader = ChoiceLoader(loaders)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["idempotency_key"] = new_idempotency_key
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
            abort(400, description="Your form expired. Reload the page and try again.")


@web.after_app_request
def _security_headers(response):
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


def _outcome_error(outcome: str, result: Any = None) -> ServiceError:
    message, status = OUTCOME_MESSAGES.get(outcome, ("We could not complete that purchase.", 400))
    if outcome == "not_enough_tickets":
        left = _field(result, "available")
        if isinstance(left, int) and left > 0:
            message = message.format(available=f"{left} ticket{'s' if left != 1 else ''}", count=left)
        else:
            message = "Sorry, there are not enough tickets left for that quantity."
    return ServiceError(outcome, message, status)


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
    flash(OUTCOME_MESSAGES["not_authenticated"][0])
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
        return _error_page(ServiceError("event-not-found", "We could not find that event.", 404))
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
                error=error.message,
                form={"name": name, "email": email, "currency": currency},
                currencies=_currencies(),
            ),
            error.status_code,
        )
    flash("Account created. Please log in.")
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
            flash("Saved. This currency is now preselected at checkout and used for Quick Buy.")
            return redirect(url_for("web.account"))
        except ServiceError as service_error:
            return _account_page(error=service_error)
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
                flash("Too many wrong passwords. For your security you have been logged out.")
                return redirect(url_for("web.login"))
        return _account_page(email_error=error)
    session.pop("email_change_failures", None)
    flash("Email changed. Student discounts now follow your new email.")
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
        flash(OUTCOME_MESSAGES["cancelled"][0])
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
            flash(REPLAYED_MESSAGE)  # purchase-014: the repeat landed on the same order
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
