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
