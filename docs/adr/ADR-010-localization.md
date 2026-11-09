# ADR-010: Localization

**Status:** `[TEAM]` accepted (Call 6). Spanish wording `[TEMPORARY_MVP_DEFAULT]` until a native speaker reviews it. Supports system-020, system-021, system-022, system-023.

## Context
Darnell's international student groups need the site in Spanish at minimum, with room for more languages, dates in the reader's regional format, and currency written the way that currency is written. Priya's condition: full path (requirements, specification, code, tests), and the yen regression test stays green.

## Decision
1. **Message catalogs, one per language.** Page text is looked up by key in a catalog. English and Spanish (neutral Latin American `es`, not Spain-specific) ship first. Adding a language means adding a catalog, not changing code.
2. **Locale comes from an allowlist.** Order: `?lang` parameter or cookie, then `Accept-Language`, then `en`. A value not in the allowlist is ignored, so a request cannot select arbitrary files or inject text.
3. **Dates** are formatted by the reader's locale (system-021).
4. **Currency amounts** are formatted by the currency's own convention (system-022): symbol placement and separators come from the locale, the number of decimals comes from the currency's minor unit ([ADR-008](ADR-008-money-formatting-and-minor-units.md)). JPY shows no decimals.
5. **Localization is presentation only.** It never changes a stored amount, rate or audit value. Money is still computed only by the pricing calculator (pricing-007). Audit and admin reason codes stay language-neutral.
6. **The yen regression test is the first gate** (system-023). Localization changes must keep it green.

## Consequences
- Templates contain keys, not hard-coded English, for the pages covered.
- Missing translation keys fall back to English rather than showing a blank.
- Some wording (legal, error messages) needs a native-speaker review before release to real users.

## Open
Further languages and right-to-left support are not part of this decision.
