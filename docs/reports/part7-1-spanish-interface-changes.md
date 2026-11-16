# Part 7, Deliverable 1: What had to change to support a Spanish user interface

**CEN 4020 AI Project, Part 7 (Configuration Management) · Team: Ian Koratsky, Minh Tam Nguyen**

The customer wants a Spanish version of EventHub. The program has to be configurable to run in English or Spanish, and when Spanish is selected the top-level menu has to be in Spanish.

## Where we started

Part 6 had already added Spanish language files (`app/i18n/en.json` and `es.json`), including every top-level menu item. A visitor could pick Spanish with `?lang=es` or their browser's language setting. Three things were still missing:

1. **A setting for the language.** English was hard-coded as the fallback, so the people running the site could not choose Spanish for everyone.
2. **Six English-only pages:** log in, register, account, error, exchange rates and audit log.
3. **35 English messages hard-coded in `app/web/__init__.py`**, such as "Account created. Please log in." and the purchase error messages.

## What we changed

### The language setting

The setting is `EVENTHUB_LANGUAGE`, with values `en` (English) or `es` (Spanish).

- When it is set, the whole site uses that language, even if the browser asks for a different one.
- A visitor can still switch language with the footer link.
- When it is not set, the site works as before.
- Any other value (for example `fr` or `spanish`) stops the app from starting, with a message that lists the allowed values.

| File | Change |
|---|---|
| `app/config/settings.py` | Reads `EVENTHUB_LANGUAGE` with the other settings. A bad value stops start-up. |
| `app/i18n/locales.py` | `configured_locale()` checks the value. `resolve_locale()` uses this order: `?lang`, the cookie, the setting, the browser language, then English. |
| `app/__init__.py` | Stores the setting for the app, and `/healthz` shows it. |
| `app/web/__init__.py` | Uses the setting when choosing each page's language. |

### The top-level menu

The menu is in `templates/base.html` (lines 60 to 77). Its text already came from the language files after Part 6, so the template did not need to change. With `EVENTHUB_LANGUAGE=es` it reads:

- for a guest: *Eventos · Historial de pedidos · Iniciar sesión · Registrarse*;
- for a signed-in user: *Eventos · Historial de pedidos · Cuenta · Administración · Cerrar sesión*.

Screenshots of the English and Spanish menus are in `docs/evidence/part7/screenshots/`.

### The rest of the interface

- **The six English-only templates.** All their visible text now comes from the language files.
- **The 35 messages in `app/web/__init__.py`.** They now come from the language files too. The English wording did not change.
- **Six fixed error messages from the account code**, for example "Invalid email or password." These are shown in Spanish, matched by their error code.
- **The language files.** They grew from 78 to 171 entries each.

### Requirements and tests

- **New requirements:** system-024 to system-027 in `features/system/requirements.md`. The design decisions are recorded in `docs/adr/ADR-011-configured-interface-language.md`.
- **New tests:**
  - unit tests for the setting;
  - contract tests that check 14 pages in Spanish;
  - six Selenium system tests (ST-71 to ST-76) that start EventHub with `EVENTHUB_LANGUAGE` set and check it in a real browser.

## What we did not change

- **15 validation messages** that the account and exchange-rate code builds from what the user typed stay in English. One example is "password must be at least 8 characters". Translating them would mean changing those modules to return error codes instead of sentences.
- **Exchange rates** are shown as `0.92` in both languages, because the admin form only accepts a dot.
- **The Spanish text** has not been checked by a native speaker.
