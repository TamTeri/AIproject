# EventHub acceptance matrix

`PASS` means an automated test proves the requirement. `PASS (temporary)` means it passes using a `[TEMPORARY_MVP_DEFAULT]` value the customer has not confirmed. `OPEN` means it is waiting on a decision.

| Requirement | Proof | Status |
|---|---|---|
| identity-001/002 register anywhere, name/email/password | `tests/unit/identity/test_service.py`, `tests/integration/test_end_to_end.py` | PASS |
| identity-003/004 login, generic failure | `test_service.py::test_login_*`, contract `test_wrong_password_shows_generic_error` | PASS |
| identity-005 hashed passwords only | `test_register_validates_and_persists_only_a_password_hash`, integration `pbkdf2_sha256$` check | PASS |
| identity-006, system-008 session expiry | `tests/unit/identity/test_sessions.py`, integration session timeout | PASS (temporary: 30 min) |
| identity-007/008/009 login required, return to page, nothing created | contract `test_protected_pages_*`, `test_unauthenticated_checkout_post_creates_nothing` | PASS |
| identity-010, orders-001 own orders only | `tests/unit/orders/test_service.py`, integration `test_buyers_only_see_their_own_orders` | PASS |
| identity-011, admin-002 buyers blocked from admin | contract `test_buyers_cannot_open_admin_pages`, `tests/unit/admin/` | PASS |
| identity-012, admin-004/005 admin provisioning | `create-admin` command, e2e `test_admin_area_end_to_end` | PASS (temporary, ADR-004 OPEN) |
| catalog-001..005 list, search artist/venue, open page, no-match | `tests/unit/catalog/`, contract | PASS |
| catalog-006 search text never markup | contract `test_catalog_search_escapes_query...` | PASS |
| catalog-007 availability on event page | contract, e2e | PASS |
| catalog-008/011, purchase-011 double-click quick buy, same path | contract `test_event_cards_support...`, `test_quick_buy_uses_saved_currency...`, unit `test_quick_buy_uses_the_same_validation...` | PASS |
| catalog-009 responsive | contract viewport check; CSS media queries | PASS (no device lab) |
| inventory-001..004 capacity, atomic, concurrent | integration `test_concurrent_buyers_never_oversell...` | PASS |
| inventory-005/006/007 10-minute hold, release, convert once | unit `test_expired_hold_*`, `test_pay_converts_hold_without_second...`, integration | PASS (temporary mechanics) |
| pricing-001/002/007 one calculator | `tests/unit/pricing/test_calculator.py` | PASS |
| pricing-003/004/005 currency choice, configured rates, admin update | `test_quote_service.py`, integration rate tests | PASS |
| pricing-006/009/010 discount policy | `test_eligibility.py` Call 4 cases | PASS (temporary: 10%, exact domain) |
| pricing-008 money representation | ADR-005, calculator tests | PASS |
| purchase-001/002/003/008 server validation, specific failures | `tests/unit/purchase/test_checkout_flow.py`, contract rejection messages | PASS |
| purchase-004 simulated payment | `SimulatedPayments`, decline tests | PASS |
| purchase-005/006, orders-002/003/004, system-006 order and on-screen confirmation, no email | contract `test_checkout_review_pay_and_confirmation`, e2e | PASS |
| purchase-009 limit | unit and integration limit tests | PASS (temporary: 4) |
| purchase-010 organizational exception | — | OPEN |
| purchase-012/013 payment failure, frozen price | unit and integration | PASS |
| audit-001/002/004/005/007 every attempt, specific outcomes, required fields | unit `test_every_attempt_is_audited...`, integration `test_rejections_are_audited...` | PASS |
| audit-003/006 admin-only viewer | contract, e2e | PASS (retention OPEN) |
| system-001/002 boundary validation, currency list | unit parse tests, contract | PASS |
| system-003/004/005 Python/Flask, one app, one database | `tests/test_main_program.py` | PASS |
| system-007 no native app, no seat map | (nothing built) | PASS |
| system-009/010/011 CI, pre-commit, definition of done | `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `CONTRIBUTING.md` | PASS |
| system-012 standalone modules, main program includes all | `tests/test_main_program.py`, ADR-006 | PASS |

## Call 5 additions

`ST-nn` are Selenium system tests in `tests/system/` (see `docs/testing/system-test-catalogue.md`).

| Requirement | Proof | Status |
|---|---|---|
| purchase-014 same form submitted twice | ST-30..35; unit `test_call5_rules.py`; PostgreSQL 5-thread same-key test | PASS (temporary: customer to confirm) |
| purchase-015 request limit | ST-36, ST-37; unit; PostgreSQL concurrent counter | PASS (temporary: 10 per 60 s) |
| purchase-016 logged-out purchase | ST-11, ST-17; contract; PostgreSQL | PASS |
| purchase-017 specific messages | ST-11, ST-13, ST-22; unit `classify_quantity`; contract | PASS |
| purchase-018 sales close at start | ST-44, ST-69; unit; PostgreSQL | PASS (temporary cut-off) |
| pricing-011 discount re-checked at payment | ST-38, ST-39; unit; PostgreSQL | PASS |
| pricing-012 email ownership verification | — | OPEN |
| identity-014 email change | ST-40; unit; contract | PASS |
| identity-015 home currency at registration | ST-42; contract; PostgreSQL | PASS |
| orders-006 labelled amount charged | ST-41; contract | PASS |
| catalog-012 currency source shown | ST-42, ST-43; contract | PASS |
| inventory-009 last-ticket race | `test_last_ticket_race_repeated_200_times`, ST-65 | PASS |
| audit-008 new reason codes | ST-11, ST-30, ST-36, ST-44 | PASS |
| system-013 performance | ST-70 (p95 ≈ 0.3 s, target 1 s) | PASS (temporary target) |
| system-014 system tests at a button | `tests/test_project_process.py`, the suite itself | PASS |
| system-015 tests trace to requirements | collection check in `tests/system/conftest.py`; `check_requirement_coverage.py` in CI | PASS |

## Call 6 additions (maintenance)

Written before the code and tests were merged, so every row starts `OPEN` or `PASS (temporary)`. Rows move to `PASS` only after the merged test run shows the named proof green. Do not claim `PASS` earlier.

| Requirement | Proof (planned) | Status |
|---|---|---|
| system-016 every currency purchased, exact total, JPY | `tests/integration/test_multicurrency.py` (PostgreSQL), `tests/unit/pricing/test_money_characterization.py` | PASS (Part 7 status update: green in CI run 42690233012 on `v1.3.0` and in the local PostgreSQL run, `docs/evidence/part7/pytest-before.log`) |
| pricing-014 minor unit for display and charge; missing exponent is an error | `tests/unit/pricing/test_presenter.py`, `test_money_characterization.py`, `tests/unit/orders/test_multicurrency_view.py` | PASS (same evidence as system-016) |
| pricing-014 JPY as a real supported currency | customer sign-off needed | OPEN (JPY seeded only for testing) |
| admin-006, pricing-013 rate edit used by next purchase; >25% confirmation; history row | `tests/integration/test_rate_edit_purchase.py` (PostgreSQL), `tests/unit/admin/test_service.py` | PASS (25% is `[TEMPORARY_MVP_DEFAULT]`; same evidence as system-016) |
| system-020 Spanish + English, allowlisted locale, order of precedence | `tests/unit/i18n/test_i18n.py`; Part 7: `test_configured_language.py::test_precedence`, ST-73, ST-74 | PASS |
| system-021 regional date format | `test_i18n.py::test_dates_per_locale`; ST-75 (Spanish date in order history) | PASS |
| system-022 currency formatted by its own conventions | `test_i18n.py::test_money_per_locale`, `::test_locale_never_changes_the_amount`; ST-75 (`24,84 EUR`) | PASS |
| system-023 localization keeps the yen test green | `tests/unit/i18n/test_yen_under_localization.py`; still green after Part 7 (`docs/evidence/part7/pytest-after.log`) | PASS |
| audit-009 out-of-range order flagged and a human notified | `tests/unit/audit/test_anomaly.py`, `tests/integration/test_order_watch.py` (PostgreSQL) | PASS (temporary: thresholds 50%-200%; recipient and rotation `[OPEN]`) |
| system-017 no promotion until corrective tests green; skipped tests fail the gate | `scripts/fail_on_skips.py`, `test_project_process.py::test_ci_fails_on_skipped_tests_and_checks_the_migration_round_trip` | PASS |
| system-018 every release restorable | tags `v1.2.0`, `v1.3.0` (created in Part 7: they were documented but missing), `v1.4.0` after merge; `docs/runbooks/release-and-rollback.md`; restore drill of `v1.3.0` in `docs/evidence/part7/` | OPEN until the tags are pushed to GitHub and `v1.4.0` is tagged |
| system-019 database backup owner, nightly `pg_dump`, restore drill | — | OPEN (no owner named) |

## Part 7 additions (configuration management: English or Spanish)

| Requirement | Proof | Status |
|---|---|---|
| system-024 `EVENTHUB_LANGUAGE` configures the language; beats `Accept-Language`; visitor choice still wins; `/healthz` shows it | `tests/unit/i18n/test_configured_language.py`, `tests/contract/test_spanish_interface.py`, `tests/test_main_program.py::test_healthz_reports_the_configured_language`; ST-71, ST-73, ST-74 | PASS |
| system-025 an unsupported value stops start-up | `test_main_program.py::test_an_unsupported_language_stops_start_up`, `test_configured_language.py::test_unsupported_values_are_refused_never_mapped_to_english` | PASS |
| system-026 top-level menu in Spanish | `test_spanish_interface.py::test_configured_spanish_*`; ST-71, ST-72 | PASS |
| system-027 every page's fixed text and web messages in Spanish | `test_spanish_interface.py::test_no_english_is_left_on_any_page_when_spanish` (14 pages), message tests, `test_untranslated_text_guard.py`; ST-75, ST-76 | PASS (temporary: Spanish wording until a native speaker reviews it; input-dependent service sentences stay English, ADR-011) |
