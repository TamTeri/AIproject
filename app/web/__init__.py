from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flask import Blueprint, Flask, abort, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader

from .services import ServiceError, WebServices, default_services

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

web = Blueprint("web", __name__)


def register_web(app: Flask, services: WebServices | Any | None = None) -> Flask:
    """Attach the buyer web boundary to an existing Flask application."""
    if "web" not in app.blueprints:
        app.register_blueprint(web)
    app.extensions["eventhub_web_services"] = services or default_services()
    existing_loader = app.jinja_loader
    app.jinja_loader = ChoiceLoader(
        [FileSystemLoader(str(_TEMPLATES)), existing_loader] if existing_loader else [FileSystemLoader(str(_TEMPLATES))]
    )
    return app


def create_web_app(
    *,
    services: WebServices | Any | None = None,
    config: Mapping[str, Any] | None = None,
) -> Flask:
    """Create an isolated Flask web app for the buyer surface and contract tests."""
    app = Flask(__name__)
    app.config.from_mapping(SECRET_KEY="eventhub-local-only", TESTING=False)
    if config:
        app.config.update(config)
    register_web(app, services)
    return app


def _services() -> Any:
    from flask import current_app

    return current_app.extensions["eventhub_web_services"]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


@web.get("/events")
def events():
    query = (str(__import__("flask").request.args.get("q", "")) or None)
    try:
        result = _services().catalog.list_events(query=query)
    except ServiceError as error:
        return render_template("error.html", error=error), error.status_code
    event_list = _field(result, "events", []) or []
    no_match = bool(_field(result, "no_match", False))
    return render_template("events.html", events=event_list, query=query, no_match=no_match)


@web.get("/events/<event_id>")
def event_detail(event_id: str):
    try:
        event = _services().catalog.get_event(event_id=event_id)
    except ServiceError as error:
        return render_template("error.html", error=error), error.status_code
    if event is None:
        error = ServiceError("event-not-found", "We could not find that event.", 404)
        return render_template("error.html", error=error), error.status_code
    return render_template("event_detail.html", event=event)


def _is_safe_relative_target(target: str | None) -> bool:
    """[TEMPORARY_MVP_DEFAULT] Only a same-origin relative path is an allowed login return target."""
    if not target:
        return False
    if not target.startswith("/"):
        return False
    if target.startswith("//"):
        return False
    if "\\" in target:
        return False
    return True


def _current_buyer_id() -> str | None:
    return session.get("buyer_id")


def _require_authenticated():
    """[TEMPORARY_MVP_DEFAULT] Safe GET redirect; session lifecycle policy remains open."""
    buyer_id = _current_buyer_id()
    if buyer_id is not None:
        return buyer_id, None
    login_url = url_for("web.login", next=request.path)
    return None, redirect(login_url)


@web.get("/login")
def login():
    next_target = request.args.get("next")
    return render_template("login.html", next_target=next_target if _is_safe_relative_target(next_target) else None)


@web.post("/login")
def login_submit():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    next_target = request.form.get("next")
    try:
        result = _services().identity.authenticate(email=email, password=password)
    except ServiceError as error:
        return render_template("error.html", error=error), error.status_code
    account = _field(result, "account", {})
    buyer_id = _field(account, "id")
    if buyer_id is None:
        error = ServiceError("invalid-credentials", "Invalid email or password.", 401)
        return render_template("error.html", error=error), error.status_code
    session["buyer_id"] = buyer_id
    destination = next_target if _is_safe_relative_target(next_target) else None
    return redirect(destination or url_for("web.events"))


@web.get("/register")
def register():
    return render_template("register.html")


@web.post("/register")
def register_submit():
    name = request.form.get("name", "")
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    try:
        _services().identity.register(name=name, email=email, password=password)
    except ServiceError as error:
        return render_template("error.html", error=error), error.status_code
    return redirect(url_for("web.login"))


@web.get("/orders")
def orders():
    buyer_id, redirect_response = _require_authenticated()
    if redirect_response is not None:
        return redirect_response
    try:
        order_list = _services().orders.list_for_buyer(buyer_id=buyer_id)
    except ServiceError as error:
        return render_template("error.html", error=error), error.status_code
    return render_template("orders.html", orders=order_list or [])


@web.get("/orders/<order_id>")
def order_detail(order_id: str):
    buyer_id, redirect_response = _require_authenticated()
    if redirect_response is not None:
        return redirect_response
    try:
        order = _services().orders.get_for_buyer(buyer_id=buyer_id, order_id=order_id)
    except ServiceError as error:
        return render_template("error.html", error=error), error.status_code
    if order is None:
        error = ServiceError("order-not-found", "We could not find that order.", 404)
        return render_template("error.html", error=error), error.status_code
    return render_template("order_detail.html", order=order)


__all__ = ["create_web_app", "register_web", "web"]
