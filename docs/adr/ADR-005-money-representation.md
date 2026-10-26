# ADR-005: Money representation

**Status:** `[TEAM]` accepted. Written before the first price was computed, as Kenji asked in Call 4. Supports pricing-001/002/003/007/008.

## Context
Floating-point money silently produces errors such as 0.1 + 0.2 = 0.30000000000000004. Currency conversion and percentage discounts make rounding visible to buyers and auditors.

## Decision
1. **Amounts are integers in the currency's minor unit** (cents for USD, EUR, GBP and CAD). The `minor_unit` column in `currencies` allows 0 to 4 decimal places, for example JPY = 0.
2. **Exchange rates are exact decimals**, stored as `NUMERIC(18, 8)` and read as Python `Decimal`, never `float`. A rate means "1 USD = rate × target currency". Rates are configured by an administrator, not fetched live (pricing-004).
3. **Base currency is USD.** Event prices are stored as `base_price_minor` in USD cents.
4. **Order of operations**, all inside `app/pricing/calculator.py:calculate_price()`:
   1. subtotal = base price × quantity (USD cents)
   2. apply the student discount, if eligible (still USD)
   3. convert to the target currency
   4. round once, `ROUND_HALF_UP`, to the target currency's minor unit
5. **Displayed subtotal − discount = total exactly.** The discount shown is the converted subtotal minus the converted total, so the receipt always adds up.
6. **Frozen quotes.** The quote is saved on the hold (`holds.quote_snapshot`) and copied to the order. Orders never recalculate a price.

## Example
2 tickets at 25.00 USD, a student buyer, paying in EUR at rate 0.92:
- 50.00 USD → 10% off → 45.00 USD
- × 0.92 = 41.40 EUR
- The receipt shows a subtotal of 46.00, a discount of −4.60 and a total of 41.40 EUR.

## Open
The discount percentage itself is `[TEMPORARY_MVP_DEFAULT]` 10% (`STUDENT_DISCOUNT_PERCENT_PLACEHOLDER`). It is still not confirmed by the customer.
