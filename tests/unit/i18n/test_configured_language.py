"""Part 7: the deployment language is configured with EVENTHUB_LANGUAGE (system-024, system-025, ADR-011)."""

from __future__ import annotations

import pytest

from app.config.settings import ConfigurationError, Settings
from app.i18n import SUPPORTED, configured_locale, resolve_locale

DB = "postgresql+psycopg://u:p@localhost:1/none"

# ------------------------------------------------------------- the setting


@pytest.mark.requirement("system-024")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("en", "en"),
        ("es", "es"),
        ("ES", "es"),
        ("  es  ", "es"),
        ("es\n", "es"),  # surrounding whitespace from a .env file is forgiven
        ("En", "en"),
        (None, None),  # not set: follow the browser
        ("", None),
        ("   ", None),
    ],
)
def test_supported_values_and_not_configured(raw, expected):
    assert configured_locale(raw) == expected


@pytest.mark.requirement("system-025")
@pytest.mark.parametrize(
    "bad", ["fr", "spanish", "Español", "es-MX", "es_419", "en-US", "e", "../es", "x" * 500]
)
def test_unsupported_values_are_refused_never_mapped_to_english(bad):
    with pytest.raises(ValueError) as caught:
        configured_locale(bad)
    message = str(caught.value)
    assert message.startswith("EVENTHUB_LANGUAGE must be one of: en, es")
    assert len(message) < 160  # an oversized value is cut, not echoed


@pytest.mark.requirement("system-024")
def test_settings_read_the_language(monkeypatch):
    monkeypatch.delenv("EVENTHUB_LANGUAGE", raising=False)
    assert Settings.from_values({"DATABASE_URL": DB}).language is None
    assert Settings.from_values({"DATABASE_URL": DB, "EVENTHUB_LANGUAGE": "es"}).language == "es"
    monkeypatch.setenv("EVENTHUB_LANGUAGE", "ES")
    assert Settings.from_values({"DATABASE_URL": DB}).language == "es"


@pytest.mark.requirement("system-025")
def test_settings_refuse_an_unsupported_language(monkeypatch):
    monkeypatch.setenv("EVENTHUB_LANGUAGE", "fr")
    with pytest.raises(ConfigurationError, match="EVENTHUB_LANGUAGE must be one of: en, es"):
        Settings.from_values({"DATABASE_URL": DB})


# --------------------------------------------------- order of precedence


@pytest.mark.requirement("system-020", "system-024")
@pytest.mark.parametrize(
    ("query", "cookie", "header", "configured", "expected"),
    [
        # configured, nothing else: the configured language
        (None, None, None, "es", "es"),
        (None, None, None, "en", "en"),
        # the configured language beats the browser's Accept-Language
        (None, None, "en-US,en;q=0.9", "es", "es"),
        (None, None, "es-MX,es;q=0.9", "en", "en"),
        # a visitor's own choice beats the configured language
        ("en", None, None, "es", "en"),
        (None, "en", None, "es", "en"),
        ("es", None, None, "en", "es"),
        # unsupported request values fall through to the configured language
        ("fr", "xx", "de", "es", "es"),
        # not configured: exactly the Call 6 order
        (None, None, "es-MX,es;q=0.9", None, "es"),
        (None, None, None, None, "en"),
    ],
)
def test_precedence(query, cookie, header, configured, expected):
    assert resolve_locale(query, cookie, header, configured=configured) == expected


@pytest.mark.requirement("system-024")
@pytest.mark.parametrize("unchecked", ["fr", "../en", "ES", "", "es-MX"])
def test_an_unchecked_configured_value_can_never_leave_the_allowlist(unchecked):
    """configured_locale() runs at start-up; resolve_locale still refuses anything outside SUPPORTED."""
    result = resolve_locale(None, None, None, configured=unchecked)
    assert result in SUPPORTED
    assert result == "en"
