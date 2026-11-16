# ADR-011: Configured interface language (English or Spanish)

**Status:** `[STAKEHOLDER]` request (Part 7: "allow the program to be configured to operate in either English or Spanish"), `[TEAM]` design. Spanish wording stays `[TEMPORARY_MVP_DEFAULT]` until a native speaker reviews it (ADR-010). Supports system-024, system-025, system-026, system-027. Refines [ADR-010](ADR-010-localization.md).

## Context
ADR-010 (Call 6) let each visitor pick a language with `?lang`, a cookie, or the browser's `Accept-Language`, with English as the fixed fallback. It did not let the people running EventHub decide the language of a deployment. The customer now wants a Spanish-language version: the program is configured to run in English or in Spanish, and when Spanish is configured the top-level menu is in Spanish.

Call 6 also left two gaps that a "Spanish version" cannot have: the log-in, register, account, error and admin pages were English only, and the messages the web pages write (for example "Account created. Please log in.") were hard-coded English sentences in `app/web/__init__.py`.

The yen incident of Call 6 is the standing lesson: a value that is wrong should stop the system, not be replaced by a silent default.

## Decision
1. **One setting, read at start-up.** `EVENTHUB_LANGUAGE` is read by `app/config/settings.py` like every other `EVENTHUB_*` setting. Allowed values are the codes in `app/i18n/locales.py` `SUPPORTED` (`en`, `es`). Absent or blank means "not configured".
2. **A wrong value stops the start-up** (system-025). `EVENTHUB_LANGUAGE=fr` or `spanish` raises `ConfigurationError` naming the allowed values. It is never mapped to English. Case and surrounding spaces are forgiven (`" ES "` is `es`); regional tags such as `es-MX` are not accepted here, because an operator setting should be exact.
3. **Order of precedence** (system-020 amended, system-024): `?lang` > cookie > **configured language** > `Accept-Language` > `en`.
   - The configured language beats `Accept-Language`, because otherwise a Spanish deployment would show English to every browser set to English, and the setting would have no visible effect.
   - A visitor's own choice still beats the configuration: the footer switcher stays, so a reader who needs English on the Spanish deployment (or the reverse) can still get it. The cookie is only ever set by an explicit `?lang` choice.
   - Not configured means exactly the Call 6 behaviour, so English deployments and the 87 existing English system tests are unchanged.
4. **Validated in one function, used in two places.** `configured_locale()` in `app/i18n/locales.py` does the check. `Settings` calls it (start-up), and `register_web()` calls it again for apps built without `Settings` (the contract-test factory), so neither path can carry an unchecked value.
5. **All fixed page text comes from the catalogs** (system-026, system-027). The six remaining templates use catalog keys. The sentences the web layer writes (flash messages, purchase outcome messages, error pages, the form-expired message) move from `app/web/__init__.py` into `en.json` and `es.json`. English stays word-for-word the same, so the English tests keep passing unchanged. The English catalog becomes the only place each English sentence is written.
6. **Service errors are shown by their code.** Feature services stay language-neutral (ADR-010 decision 5). For a `ServiceError` whose code always carries the same sentence (`invalid-credentials`, `wrong-password`, `unsupported-currency`, `forbidden`, `service-unavailable`, `email-taken`), the web layer shows the catalog's sentence for that code. Codes whose sentence is built from the input (`invalid-registration`, `invalid-email`, `invalid-rate`) keep the service's English sentence. Translating them needs the identity and admin services to return one code per rule instead of a sentence, which is outside this change.
7. **Codes stay codes.** The audit viewer's outcome and reason columns, currency codes and `data-error-code` attributes are not translated: they are identifiers that administrators, tests and the audit log compare.
8. **A guard keeps English from creeping back.** `scripts/find_untranslated_text.py` lists visible text in templates that is not a catalog lookup, and string literals passed to `flash()`, `abort()` or `ServiceError()` in `app/web/`. A unit test fails if it finds any. This scanner is also how the code to change was found (see the Part 7 tracing report).
9. **The running configuration is visible.** `/healthz` reports `"language": "es"`, `"en"`, or `"browser"` (not configured), next to the release version and Alembic head, so whoever deploys can check which configuration is live.
10. **Release 1.4.0.** The configured language is a new feature, so the version moves from 1.3.0 to 1.4.0.

## Consequences
- Adding a third language is still "add a catalog file", plus adding its code to `SUPPORTED`; the setting accepts it automatically.
- Deployments that do not set `EVENTHUB_LANGUAGE` behave exactly as release 1.3.0.
- `run-local.cmd -Language es` and `./run-local.sh --language es` start a local Spanish deployment for demonstration.

## Open
- Native-speaker review of all Spanish text (now about 200 entries instead of 78).
- Translating the input-dependent service sentences (decision 6).
- Further languages and right-to-left support (unchanged from ADR-010).
