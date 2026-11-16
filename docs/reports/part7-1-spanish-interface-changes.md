# Part 7, Deliverable 1: What had to change to support a Spanish user interface

**CEN 4020 AI Project, Part 7 (Configuration Management) · Team: Ian Koratsky, Minh Tam Nguyen**

The customer asked for a Spanish-language version of EventHub: the program must be configurable to run in English or in Spanish, and when Spanish is selected the top-level menu must be in Spanish. This document lists what we changed and why. How we used the GenAI tool to find each piece of code is in [Deliverable 2](part7-2-genai-tracing-report.md).

## 1. Starting point: what Part 6 had already built

Call 6 (the maintenance call) included Darnell's request for Spanish, so Part 6 already added:

- message catalogs `app/i18n/en.json` and `es.json` (78 keys each), including every top-level menu entry (`nav_events`, `nav_orders`, `nav_account`, `nav_admin`, `nav_logout`, `nav_login`, `nav_register`);
- a per-visitor language choice: `?lang=es`, a cookie, or the browser's `Accept-Language`, falling back to English;
- Spanish dates (`dom, 1 nov 2026 · 19:00`) and amounts (`24,84 EUR`);
- translated buyer pages: events, event detail, checkout, order confirmation, order history.

So a Spanish menu already existed for a visitor who asked for it. Three things were missing for Part 7:

| Gap | Why it matters for Part 7 |
|---|---|
| **No configuration.** The language was each visitor's choice; English was hard-coded as the fallback (`DEFAULT_LOCALE = "en"`). | The customer asked for a *program* configured to run in English or Spanish. An English-language browser always saw English, whatever the operator wanted. |
| **Six pages still English**: log in, register, account, error, exchange rates, audit log. | A "Spanish version" whose log-in page is English is not one. |
| **35 sentences hard-coded in `app/web/__init__.py`**: flash messages ("Account created. Please log in."), purchase rejections, error pages. | These appear on Spanish pages after every action. |

## 2. What we changed, layer by layer

### Requirements (written first)
`features/system/requirements.md`, tagged `[Part 7]`:

| Id | Requirement (short) |
|---|---|
| system-024 | `EVENTHUB_LANGUAGE=en` or `es` configures the language. It beats the browser's `Accept-Language`; a visitor's own `?lang`/cookie choice still wins. Not set means the Call 6 behaviour. `/healthz` reports it. |
| system-025 | An unsupported value (`fr`, `spanish`, `es-MX`) stops start-up and names the allowed values; it never falls back to English. |
| system-026 | While Spanish, every top-level menu option and the language-switcher label are in Spanish. |
| system-027 | While Spanish, every page's fixed text and the messages the web pages write are in Spanish. Input-dependent service sentences may stay English (listed in ADR-011). |

system-020 was amended to record the new order of precedence.

### Design
- **[ADR-011](../adr/ADR-011-configured-interface-language.md)**, "Configured interface language", records ten decisions. The main ones are: one setting read at start-up; a wrong value stops the app (the Call 6 lesson that a silent default is how 4,500 yen became 45); the precedence `?lang` > cookie > **configured** > `Accept-Language` > `en`; every page and web message from the catalogs; service errors shown by their code; codes never translated.
- **Model (`workspace.dsl`)**: a new person, *Operator*, who sets `EVENTHUB_LANGUAGE` and reads `/healthz`; the Localization component's description now includes the configured language; new views `Container_PostCall7` and `Component_PostCall7`. Every earlier view excludes the `PostCall7` tag, so the old diagrams are unchanged. The file was checked with `structurizr/structurizr validate` (exit 0; a deliberately broken copy fails with exit 1).

### Configuration (the core of Part 7)

| File | Change |
|---|---|
| `app/i18n/locales.py` | New `configured_locale()` (line 52): blank means "not configured"; a supported code, ignoring case and spaces, is accepted; anything else raises `ValueError` with the allowed values. `resolve_locale()` (line 72) takes `configured=` and checks it against the allowlist again (line 87). |
| `app/config/settings.py` | `Settings.language` (line 23), read from `EVENTHUB_LANGUAGE` with every other `EVENTHUB_*` setting (line 39). A bad value becomes `ConfigurationError`, so the app does not start (line 50). |
| `app/__init__.py` | `create_app()` stores the checked code, never the raw text (line 39). `/healthz` reports `"language"` (line 58). |
| `app/web/__init__.py` | `register_web()` checks the value again for apps built without `Settings` (line 99). The per-request `_resolve_locale()` passes the configured language (lines 140 to 146). |
| `run-local.cmd -Language es`, `./run-local.sh --language es` | Start a local Spanish deployment for demonstration. |

### The top-level menu
The menu is in `templates/base.html`, lines 60 to 77 (`<nav>`), with the language switcher at line 88. Its text was already catalog keys after Part 6, so the menu's markup did not change; we only added a comment naming system-026 above it (line 58), so the requirement can be traced to it. What changed is **who decides the language**: with `EVENTHUB_LANGUAGE=es` the menu reads *Eventos · Historial de pedidos · Iniciar sesión · Registrarse* (guest) or *Eventos · Historial de pedidos · Cuenta · Administración · Cerrar sesión (name)* (signed in), even for a browser that asks for English. Screenshots: `docs/evidence/part7/screenshots/`.

### The rest of the interface

| What | Change |
|---|---|
| `templates/login.html`, `register.html`, `account.html`, `error.html`, `admin_rates.html`, `admin_audit.html` | Every visible text, including the `<title>` and the `aria-label` on the rate inputs, is now a catalog lookup `{{ _('key') }}`. The HTML structure, ids and form fields are unchanged. |
| `app/web/__init__.py` | `OUTCOME_MESSAGES` (sentence, status) became `OUTCOME_ERRORS` (catalog key, status). All seven flash messages, the four error-page sentences and the expired-form message go through `_t(key)`. "Only N ticket(s) left" now has its own *one* and *other* keys, so Spanish gets correct plurals. |
| Service errors | `SERVICE_ERROR_KEYS` maps six error codes whose sentence never changes (`invalid-credentials`, `wrong-password`, `unsupported-currency`, `email-taken`, `forbidden`, `service-unavailable`) to catalog keys. `_localized()` shows the page-language sentence. The services themselves were not changed. |
| `app/i18n/en.json`, `es.json` | 78 keys each became **171** each (93 added). The English entries are the old sentences, word for word. |
| Version | `pyproject.toml` 1.3.0 became **1.4.0** (a new configurable feature). |

### Tests
| Layer | New or changed |
|---|---|
| Unit | `tests/unit/i18n/test_configured_language.py`: accepted and refused values, the precedence table, and that an unchecked value can never leave the allowlist. `test_untranslated_text_guard.py` fails if any template or web-layer English appears (see Deliverable 2). |
| Contract (fake services) | `tests/contract/test_spanish_interface.py`: the menu for guest, buyer and administrator; 14 pages checked for leftover English, with the same 14 pages in English as a control; every purchase rejection, flash message and fixed-sentence service error in Spanish; English unchanged word for word against the 1.3.0 sentences. |
| Main program | `/healthz` language; `EVENTHUB_LANGUAGE` from the environment; six bad values refuse to start; version 1.4.0. |
| Selenium | ST-71 to ST-76 (`tests/system/test_st_part7_language.py`) start a second EventHub with `EVENTHUB_LANGUAGE` set, as an operator would. `make_driver()` now pins the browser to English, so no test depends on the language of the machine running it. |

### Documents
README (a "Language" section and a table of the settings), CONTRIBUTING (rules for text and how to add a language), the release runbook (1.4.0 adds no migration; the rollback caveat below), `docs/testing/system-test-cases.md`, the regenerated system-test catalogue, the acceptance matrix, and `IMPLEMENTATION_STATUS.md`.

## 3. Why these changes, in plain language

1. **A setting, not a code change.** Configuration management means the same released code runs as the English or the Spanish version, and the difference is recorded in one named setting. Nobody edits code or templates to switch.
2. **A wrong setting stops the app.** `EVENTHUB_LANGUAGE=spanish` is almost certainly a typo. If it quietly meant English, the Spanish deployment would go live in English and nobody would know until a student complained, the same "found out from a group chat" pattern as Call 6.
3. **The configuration beats the browser, and the visitor beats the configuration.** Without the first rule the setting would have no visible effect, because most browsers ask for English. Without the second, a reader who needs English on the Spanish site would be stuck.
4. **English stays exactly as it was.** Every English sentence moved into `en.json` unchanged, and a test compares them with release 1.3.0's text. The 87 existing English system tests ran unchanged.
5. **Codes stay codes.** Error codes, audit outcomes and currency codes are compared by people, tests and the audit log, so they are never translated.

## 4. What we did not change, and why

| Left as is | Reason |
|---|---|
| Sentences the identity and admin services build from the input (15: "password must be at least 8 characters", "Rate must be a number.", ...) | They are built per validation rule inside the services. Translating them properly means the services return one code per rule, which changes the identity and admin modules and their unit tests: a separate change. They are listed by `find_untranslated_text.py --all` and in ADR-011. Mostly admins see them, or buyers who get past the browser's own form checks. |
| Native-speaker review | The Spanish is ours and `[TEMPORARY_MVP_DEFAULT]` until the customer's reviewer checks it (now about 170 entries). |
| More languages | Out of scope. Adding one is a catalog file plus one entry in `SUPPORTED`; the setting then accepts it. |

## 5. Configuration items and baselines

| Item | Where | Values |
|---|---|---|
| `EVENTHUB_LANGUAGE` | environment, read by `Settings` | `en`, `es`, or not set |
| Message catalogs | `app/i18n/en.json`, `es.json` | 171 keys each, identical key sets (test) |
| Supported languages | `app/i18n/locales.py` `SUPPORTED` | `("en", "es")` |
| Release | `pyproject.toml`, `/healthz` | 1.4.0 |
| Baselines | git tags | `v1.2.0` (`ede191a`) and `v1.3.0` (`2a39d28`) were documented in Part 6 but did not exist, so we created them on the commits whose CI runs were green. `v1.4.0` will be tagged after this branch merges with a green CI run. |

**Rollback caveat (in the runbook).** Release 1.3.0 does not know `EVENTHUB_LANGUAGE`. Rolling back from 1.4.0 to 1.3.0 is code only (1.4.0 adds no migration), but a Spanish-configured deployment would then show English to English browsers. `/healthz` makes this visible: 1.3.0 has no `language` field.

## 6. Proof that it still passes its tests

See [Deliverable 2, section "Verification"](part7-2-genai-tracing-report.md#verification) and `docs/evidence/part7/`.
