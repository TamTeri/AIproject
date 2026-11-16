# Part 7, Deliverable 2: How we used the GenAI tool to find the code that had to change

**CEN 4020 AI Project, Part 7 (Configuration Management) · Team: Ian Koratsky, Minh Tam Nguyen**

To make EventHub configurable for English or Spanish, we first had to trace the requirement to the code that implements it. This report explains how we used the GenAI tool to do that tracing, what it found, and how we checked the result. The list of changes is in [Deliverable 1](part7-1-spanish-interface-changes.md).

## Summary

We gave the GenAI tool the assignment and the repository. We asked it to find the code that had to change for a Spanish version. It broke the job into four questions:

1. Where is the top-level menu, and where does its text come from?
2. Who decides the language, and where should a setting go?
3. Where else does English show up on the screen?
4. Which tests depend on the current English text?

It answered them with three tools: graphify, a code graph that shows what calls what; a scanner it wrote that lists the English a user can see; and a requirement tracer it wrote that lists the code and tests naming a requirement.

The main thing it found was that the Spanish menu already existed from Part 6, but there was no setting to choose the language for the whole site. The scanner also found 96 pieces of untranslated English in six templates and in the web routes.

## Step 1: Tracing the menu and the language choice

We rebuilt the code graph first. The old graph was from before Part 6 added the Spanish code, so it would have pointed at code that no longer existed. Then we ran these queries:

| Query | What it showed |
|---|---|
| `graphify explain "base.html"` | The menu is in `templates/base.html`, and all 11 pages extend it. |
| `graphify explain "translate"` | The menu text comes from the language files through `translate()` in `app/i18n/catalog.py`. |
| `graphify explain "_resolve_locale"` | This function runs before every request and picks the language. The setting had to be used here. |
| `graphify explain "register_web()"` | The app can be built two ways (`create_app()` and `create_web_app()`), so the setting had to be checked in both. |
| `graphify affected "app/i18n/locales.py"` | The tests that depend on the language code. We ran these first after each change. |

Putting these together, the path from the setting to the menu text is:

`EVENTHUB_LANGUAGE` → `Settings.from_values()` (`app/config/settings.py`) → `create_app()` (`app/__init__.py`) → `_resolve_locale()` (`app/web/__init__.py`) → `resolve_locale()` (`app/i18n/locales.py`) → `translate()` (`app/i18n/catalog.py`) → the menu in `templates/base.html`

The graph could not link a template's `_('nav_events')` to the entry in `es.json`, so we confirmed that part by reading `base.html` and the language files.

## Step 2: Finding every piece of visible English

`grep` could not tell a sentence like "Account created." from an error code or a log message. So the GenAI tool wrote `scripts/find_untranslated_text.py`, which lists:

- the visible text in each template;
- the sentence-like strings in the web routes.

Before the change it found 96 texts:

| File | Count |
|---|---|
| `app/web/__init__.py` | 35 |
| `templates/account.html` | 15 |
| `templates/admin_audit.html` | 14 |
| `templates/admin_rates.html` | 13 |
| `templates/register.html` | 10 |
| `templates/login.html` | 7 |
| `templates/error.html` | 2 |

That became our work list. After the change it finds 0, and it now runs as a unit test.

The first version of the scanner had four bugs, which we found by comparing its output with the files:

- it crashed when printing an arrow character on Windows;
- it gave some lines the wrong number;
- it flagged the currency code `USD` as English;
- it missed messages written in lower case.

We fixed all four before relying on it.

## Step 3: Where the setting should go

All other settings are read in `Settings.from_values()` (`app/config/settings.py`), so the language setting went there too. A wrong value stops the app at start-up, the same way other bad settings already do.

The order we used is: the visitor's own choice first, then the setting, then the browser language. If the setting came after the browser language, it would almost never take effect, because most browsers ask for English. Putting the visitor's choice first means someone who needs English can still get it on the Spanish site. These decisions are written down in ADR-011.

## Step 4: Effect on the tests

The tool counted which test files contain each English sentence it was about to move. For example, "Invalid email or password." appears in 2 files. So we kept every English sentence exactly the same.

The existing Selenium tests click buttons by their English labels. So they keep running against an English server, and the new Spanish tests find fields by id instead.

## Step 5: Requirements traced to code and tests

`scripts/trace_requirement.py` lists every file that names a given requirement. It showed that `base.html` did not name the menu requirement (system-026), so we added that comment.

| Requirement | Code | Tests |
|---|---|---|
| system-024: the setting chooses the language | `app/config/settings.py`, `app/i18n/locales.py`, `app/__init__.py`, `app/web/__init__.py` | `test_configured_language.py`, `test_spanish_interface.py`, `test_main_program.py`; ST-71, ST-73, ST-74 |
| system-025: a wrong value stops start-up | `app/config/settings.py`, `app/i18n/locales.py` | `test_main_program.py`, `test_configured_language.py` |
| system-026: Spanish top-level menu | `templates/base.html`, `nav_*` entries in `es.json` | `test_spanish_interface.py`; ST-71, ST-72 |
| system-027: every page and message in Spanish | six templates, `app/web/__init__.py`, the language files | `test_spanish_interface.py`, `test_untranslated_text_guard.py`; ST-75, ST-76 |

## Proof that the system still passes its tests

| | Before | After |
|---|---|---|
| Unit, contract and PostgreSQL tests | 422 passed, 0 skipped | 545 passed, 0 skipped |
| Selenium system tests | 87 of 87 passed | 93 of 93 passed |

The logs and the Selenium HTML report are in `docs/evidence/part7/`.

We also wanted to be sure the new tests could actually fail. We broke the feature on purpose so that the browser's language won over the setting. 34 tests and two Selenium tests failed, and they all passed again once the code was put back.

## Problems we ran into

| Problem | What we did |
|---|---|
| The code graph was older than the code | Rebuilt it before using it |
| Four bugs in the first version of the scanner | Fixed them before trusting its output |
| A new test wrongly expected no cookie on a Spanish page | Fixed the test; the app was correct |

## Appendix: our request to the tool

Lightly edited for spelling:

> Examine the repo carefully and follow what week 7 has to do.

The GenAI tool then did the tracing and the changes described in this report.
