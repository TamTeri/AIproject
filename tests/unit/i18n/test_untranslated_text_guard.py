"""Part 7 guard: no user-visible English outside the catalogs (system-027, ADR-011 decision 8).

scripts/find_untranslated_text.py was used to find the code to change for the Spanish
interface. Kept as a test, it fails as soon as someone adds hard-coded English to a
template or to the web layer.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _scanner():
    name = "find_untranslated_text"
    if name not in sys.modules:  # dataclasses need the module registered while it loads
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@pytest.mark.requirement("system-027")
def test_templates_and_web_layer_have_no_hard_coded_english():
    findings = _scanner().scan()
    assert findings == [], "\n".join(str(f) for f in findings)


@pytest.mark.requirement("system-027")
def test_scanner_finds_planted_english_in_a_template(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '{% extends "base.html" %}\n'
        "{% block title %}{{ _('x') }} · EventHub{% endblock %}\n"
        "<h1>Hello there</h1>\n"
        '<input aria-label="Click me" placeholder="{{ row.rate }}">\n'
        "<p>{{ _('ok') }} <strong>USD</strong> → —</p>\n"
        "<style>body { color: red }</style>\n",
        encoding="utf-8",
    )
    found = [(f.line, f.text) for f in _scanner().scan_template(page)]
    assert found == [(3, "Hello there"), (4, 'aria-label="Click me"')]


@pytest.mark.requirement("system-027")
def test_scanner_finds_planted_sentences_in_python(tmp_path):
    module = tmp_path / "routes.py"
    module.write_text(
        '"""Module docstring is not shown to anyone."""\n'
        "def view():\n"
        '    """Neither is this one."""\n'
        '    flash("Saved it.")\n'
        '    log.warning("could not record the attempt")\n'
        '    raise ServiceError("bad-code", f"Rate for {code} is wrong.", 400)\n',
        encoding="utf-8",
    )
    found = [(f.line, f.text) for f in _scanner().scan_python(module, "web")]
    assert found == [(4, "Saved it."), (6, "Rate for {…} is wrong.")]


@pytest.mark.requirement("system-027")
def test_service_sentences_are_labelled_by_how_they_are_shown():
    scanner = _scanner()
    findings = [f for f in scanner.scan(include_services=True) if f.kind.startswith("service")]
    by_code = {f.text for f in findings if f.kind == "service, shown by code"}
    english = {f.text for f in findings if f.kind == "service, stays English"}
    assert "Invalid email or password." in by_code
    assert "This EventHub service is temporarily unavailable." in by_code
    assert "Rate must be a number." in english  # built per rule: ADR-011 decision 6
    assert "password must be at least 8 characters" in english
