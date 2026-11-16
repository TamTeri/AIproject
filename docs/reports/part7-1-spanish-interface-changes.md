# Part 7, Deliverable 1: What had to change to support a Spanish user interface

**CEN 4020 AI Project, Part 7 (Configuration Management) · Team: Ian Koratsky, Minh Tam Nguyen**

The customer wants a Spanish version of EventHub. The program has to be configurable to run in English or Spanish, and when Spanish is selected the top-level menu has to be in Spanish. This document lists what we changed and why. How we found the code to change is in [Deliverable 2](part7-2-genai-tracing-report.md).

## 1. Where we started

Darnell asked for Spanish during Call 6, so Part 6 had already added some of it:

- **Language files.** `app/i18n/en.json` and `es.json`, with 78 entries each, including every top-level menu item.
- **A per-visitor choice.** Each visitor could pick a language with `?lang=es`, a cookie, or their browser's language setting. Otherwise the site fell back to English.
- **Spanish formats.** Dates like `dom, 1 nov 2026 · 19:00` and amounts like `24,84 EUR`.
- **Translated buyer pages.** Events, event details, checkout, order confirmation and order history.

So the Spanish menu already existed, but only for visitors who asked for Spanish. Three things were still missing:

| Missing | Why it mattered |
|---|---|
| A setting for the language | The language was each visitor's choice, and English was hard-coded as the fallback. Anyone whose browser was set to English always saw English, whatever the people running the site wanted. |
| Six English-only pages | Log in, register, account, error, exchange rates and audit log. A Spanish version with an English log-in page isn't really a Spanish version. |
| 35 messages hard-coded in `app/web/__init__.py` | Messages like "Account created. Please log in.", purchase errors and error pages. They appear after almost every action. |

## 2. What we changed

### Requirements (written first)

We added four requirements to `features/system/requirements.md`, tagged `[Part 7]`:

| Id | Requirement |
|---|---|
| system-024 | `EVENTHUB_LANGUAGE=en` or `es` sets the language. It takes priority over the browser's language, but a visitor's own `?lang` choice still wins. If the setting is not used, the site behaves as before. `/healthz` shows the setting. |
| system-025 | Any other value (`fr`, `spanish`, `es-MX`) stops the app from starting, with a message listing the allowed values. It never quietly falls back to English. |
| system-026 | When the language is Spanish, every top-level menu item and the language-switcher label are in Spanish. |
| system-027 | When the language is Spanish, the fixed text of every page and the messages the pages show are in Spanish. Some messages that the account and exchange-rate code builds from what the user typed may stay in English (listed in ADR-011). |

We also updated system-020 to describe the new order of precedence.

### Design

- **New decision record.** [ADR-011](../adr/ADR-011-configured-interface-language.md), "Configured interface language", records the decisions:
  - one setting, read when the app starts;
  - a wrong value stops the app, the lesson from Call 6, where a silent default turned 4,500 yen into 45;
  - the order of precedence: `?lang`, then the cookie, then the setting, then the browser language, then English;
  - every page and message comes from the language files;
  - errors from the services are translated by their error code;
  - codes (error codes, audit outcomes, currency codes) are never translated.
- **Model (`workspace.dsl`).** We added an Operator, the person who sets `EVENTHUB_LANGUAGE`. The Localization component now mentions the setting, and there are two new views, `Container_PostCall7` and `Component_PostCall7`. The older views leave the new parts out, so the earlier diagrams don't change. Structurizr validates the file.

### The setting

| File | Change |
|---|---|
| `app/i18n/locales.py` | New function `configured_locale()` (line 52). Empty means "not set". `en` or `es`, in any case and with spaces trimmed, is accepted. Anything else raises an error that lists the allowed values. `resolve_locale()` (line 72) now takes the configured language and checks it again against the allowed list. |
| `app/config/settings.py` | `Settings` has a new `language` field (line 23), read from `EVENTHUB_LANGUAGE` along with the other `EVENTHUB_*` settings (line 39). A bad value raises `ConfigurationError`, so the app does not start (line 50). |
| `app/__init__.py` | `create_app()` stores the checked value (line 39), and `/healthz` reports it as `"language"` (line 58). |
| `app/web/__init__.py` | `register_web()` checks the value again for apps built without `Settings` (line 99). The function that picks each request's language now uses the setting (lines 140 to 146). |
| `run-local.cmd`, `run-local.sh` | `run-local.cmd -Language es` and `./run-local.sh --language es` start the Spanish version locally. |

### The top-level menu

The menu is in `templates/base.html`, lines 60 to 77, and the language switcher is at line 88. After Part 6 its text already came from the language files, so the menu itself didn't need to change; we only added a comment naming system-026 above it (line 58). What changed is who decides the language.

With `EVENTHUB_LANGUAGE=es` the menu shows *Eventos · Historial de pedidos · Iniciar sesión · Registrarse* to a guest, and *Eventos · Historial de pedidos · Cuenta · Administración · Cerrar sesión (name)* to a signed-in user. It does this even when the browser asks for English. Screenshots are in `docs/evidence/part7/screenshots/`.

### The rest of the interface

| What | Change |
|---|---|
| `login.html`, `register.html`, `account.html`, `error.html`, `admin_rates.html`, `admin_audit.html` | All visible text, including page titles and the labels on the rate inputs, now comes from the language files. The HTML structure, ids and form fields are the same. |
| `app/web/__init__.py` | The purchase error messages, the seven flash messages, the error pages and the "form expired" message now come from the language files. "Only N tickets left" has separate one-ticket and many-tickets versions, so the Spanish plural is right. |
| Errors from the services | Six error codes always come with the same sentence, for example `invalid-credentials` ("Invalid email or password."). These are now shown in the page language. The services themselves didn't change. |
| `en.json`, `es.json` | Grew from 78 to 171 entries each. The English entries are the old sentences, unchanged. |
| Version | 1.3.0 became 1.4.0. |

### Tests

| Level | What we added |
|---|---|
| Unit | Which setting values are accepted or refused; the order of precedence; a check that the scanner finds no English left in templates or web routes. |
| Contract (no database) | The menu for a guest, a buyer and an admin. 14 pages checked for leftover English, with the same pages in English as a control. Every purchase error, flash message and fixed error message in Spanish. English unchanged compared with 1.3.0. |
| Main program | `/healthz` shows the language; the environment variable works; six bad values stop start-up; the version is 1.4.0. |
| Selenium | ST-71 to ST-76 start a second EventHub with `EVENTHUB_LANGUAGE` set and check it in a real browser. The test browser's own language is now fixed to English, so results don't depend on the computer running them. |

### Documents

- **README:** a new "Language" section explaining the setting.
- **CONTRIBUTING:** rules for adding text, and how to add a new language.
- **Release runbook:** release 1.4.0 has no migration, plus the rollback note below.
- **Testing documents:** the system test case list and the regenerated test catalogue.
- **Status documents:** the acceptance matrix and `IMPLEMENTATION_STATUS.md`.

## 3. Why we made these changes

1. **A setting instead of a code change.** The same release runs as either the English or the Spanish version. The only difference is one named setting, so nobody has to edit code or templates to switch.
2. **A wrong setting stops the app.** `EVENTHUB_LANGUAGE=spanish` is almost certainly a typo. If it quietly meant English, the "Spanish" site would go live in English and nobody would notice until a student complained, like the group-chat incident in Call 6.
3. **The setting beats the browser, and the visitor beats the setting.** If the setting came after the browser language it would almost never take effect, because most browsers ask for English. Letting the visitor's own choice win means someone who needs English can still get it on the Spanish site.
4. **English stays the same.** Every English sentence moved into `en.json` unchanged, and a test compares them with release 1.3.0. The 87 existing English system tests still pass without changes.
5. **Codes stay codes.** Error codes, audit outcomes and currency codes are compared by people, tests and the audit log, so we don't translate them.

## 4. What we didn't change

| Left as is | Reason |
|---|---|
| 15 messages that the account and exchange-rate code builds from the input, such as "password must be at least 8 characters" and "Rate must be a number." | Translating them means changing those modules to return a code for each rule instead of a sentence. That is a separate change. Mostly admins see them, or users who get past the browser's own form checks. They are listed in ADR-011. |
| Exchange rates shown as `0.92` rather than `0,92` | The admin rate form only accepts a dot, so showing a comma next to it would invite typing mistakes. |
| Review by a native speaker | We wrote the Spanish ourselves. It stays marked temporary until the customer's reviewer checks it. |
| More languages | Not needed yet. Adding one means adding a language file and one entry in the list of supported languages. |

## 5. Configuration items

| Item | Where | Values |
|---|---|---|
| `EVENTHUB_LANGUAGE` | Environment variable, read by `Settings` | `en`, `es`, or not set |
| Language files | `app/i18n/en.json`, `es.json` | 171 entries each, same keys in both (checked by a test) |
| Supported languages | `SUPPORTED` in `app/i18n/locales.py` | `en`, `es` |
| Release | `pyproject.toml`, `/healthz` | 1.4.0 |
| Release tags | git | `v1.2.0` (`ede191a`) and `v1.3.0` (`2a39d28`). The Part 6 documents mentioned them, but they didn't exist, so we created them on the commits whose CI runs passed. `v1.4.0` comes after this branch is merged and CI passes. |

**Rollback note (also in the runbook).** Release 1.3.0 doesn't know about `EVENTHUB_LANGUAGE`. Rolling back from 1.4.0 only means switching the code, because there is no migration. But a deployment set to Spanish would go back to following each visitor's browser language. `/healthz` shows this: 1.3.0 has no `language` field.

## 6. Proof that it still passes its tests

See [Deliverable 2, "Verification"](part7-2-genai-tracing-report.md#verification) and the logs in `docs/evidence/part7/`.
