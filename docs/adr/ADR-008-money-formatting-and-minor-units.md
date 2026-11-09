# ADR-008: Money formatting follows the currency's minor unit

**Status:** `[TEAM]` accepted (Call 6). Refines [ADR-005](ADR-005-money-representation.md); it does not replace it. Supports pricing-014, system-016, system-022.

## Context
ADR-005 already said amounts are integers in the currency's minor unit and that JPY has 0 decimals. A display cleanup (in the Call 6 scenario, release 1.3; this repository never shipped it, and our own `v1.3.0` is the fix release) formatted all money with two decimals and divided every amount by 100 at display and at charge. A 4,500-yen ticket became 45 yen, and three students bought tickets at about 1% of the price. No automated test purchased in yen, so nothing failed.

The rule was written down but not enforced in the one place where display and charge are formatted.

## Decision
1. **One source for the exponent.** The number of decimal places comes only from the currency's `minor_unit` in the `currencies` table. No code path writes `2`, `100` or `/ 100` for money.
2. **A missing exponent is an error.** If a currency has no `minor_unit`, formatting and charging raise an error. They never fall back to a default of 2. A wrong default is exactly how the incident happened.
3. **Display and charge share the same conversion.** The amount shown and the amount charged use the same minor-unit handling, so they cannot disagree.
4. **Every supported currency has a purchase test** that asserts the exact total, including a zero-decimal currency (system-016). Adding a currency without such a test fails the run.
5. **JPY is seeded for testing.** Offering JPY to real buyers needs customer sign-off `[OPEN]`.
6. **Localized formatting (ADR-010) sits on top.** Locale decides separators and symbol placement; the minor unit decides the number of decimals.

## Consequences
- ADR-005 steps (integer minor units, one rounding) are unchanged.
- A future "standardize formatting" cleanup hits the yen test first.
- A new currency needs three things: a `minor_unit`, a rate, and a purchase test.

## Open
JPY availability to real buyers is `[OPEN]` until the customer signs off.
