# Part 6, Deliverable 1: Design changes after Discussion #6 (Call 6: Maintenance)

**CEN 4020 AI Project, Part 6 Â· Team: Ian Koratsky, Minh Tam Nguyen**

Call 6 was held five weeks after launch, two days after the rate-update incident. It opened with a postmortem, produced a corrective list from Thuy, an alert and a backup question from Darnell, Priya and Kenji, and ended with Darnell's first post-launch feature request: Spanish, regional dates and currency written the way each currency is written. All of it changed the design.

Below, each change lists what Call 6 said, what we changed (requirements, model, design, code, tests), and why. New requirements are tagged `[Call 6]` in `features/*/requirements.md`. The decisions are in [ADR-008](../adr/ADR-008-money-formatting-and-minor-units.md) (money), [ADR-009](../adr/ADR-009-release-restore-backup-and-order-alert.md) (release gate, restore, backup, alert) and [ADR-010](../adr/ADR-010-localization.md) (localization). The changed C4 views are `Container_PostCall6` and `Component_PostCall6` in `workspace.dsl`. Procedures are in `docs/runbooks/`.

---

## 0. What is real and what is scenario: read this first

- **The incident is scenario-derived.** This repository never deployed a release 1.2 or 1.3, and no student was ever charged 45 yen. The Call 6 story is the assignment's scenario. We treated it as if real because the lessons apply, but we do not claim it happened.
- **Release names are mapped onto git tags.** The baseline commit (the Part 5 result) is tagged `v1.2.0`. The maintenance release is `1.3.0` (`/healthz` reports it; `test_release_version_is_1_3_0`).
- **The exact bug could not occur in our seeded product.** Before this work, ADR-005 already permitted JPY (0 decimals) but JPY was not seeded, so the 4,500-yen to 45-yen failure was impossible with the seeded currencies. The **same latent pattern did exist**, and we removed it:
  - a silent default exponent of 2 in `app/orders/service.py`, `app/purchase/models.py` and `app/pricing/config.py`;
  - a hardcoded `("USD", 2)` list price in two places;
  - a contract-test fake that formatted money with `/100:.2f`, so a test would have agreed with the bug.
  A missing exponent is now an error, never a default (pricing-014, ADR-008).
- **The database is PostgreSQL, not a file.** Kenji's "is anyone backing that file up?" is answered for PostgreSQL (`pg_dump`, `docs/runbooks/backup-restore.md`).

## 1. Every Call 6 item, traced to requirement, design, code and test

Test paths are under `tests/`. A test marked "PostgreSQL" runs only when `EVENTHUB_TEST_DATABASE_URL` is set; see section 7 for what has and has not been run.

| Call 6 item | Requirement | Design element | Code | Test |
|---|---|---|---|---|
| Corrective 1: purchase in every currency, especially yen, exact total | system-016, pricing-014 | ADR-008 rules 1 to 4; per-currency expectation table | `app/pricing/calculator.py`, `app/pricing/presenter.py` | `unit/pricing/test_money_characterization.py::test_literal_totals`, `::test_yen_is_never_shown_as_two_decimals`; `integration/test_multicurrency.py::test_purchase_in_each_enabled_currency` (PostgreSQL) and `::test_every_enabled_seed_currency_has_a_hand_derived_expectation` (fails if a currency lacks a test) |
| Corrective 3: the display fix, done properly (one source for the exponent, no default) | pricing-014 | ADR-008; `present_breakdown` shared by checkout, confirmation and history | `app/pricing/presenter.py`, `app/orders/service.py`, `app/purchase/models.py`, `app/pricing/config.py` | `unit/pricing/test_presenter.py::test_quote_snapshot_requires_exponent`, `::test_snapshot_json_without_exponent_is_rejected`, `::test_pricing_policy_requires_currency_and_exponent`; `unit/orders/test_multicurrency_view.py::test_snapshot_without_exponent_raises`, `::test_jpy_order_shows_whole_yen_and_usd_list_price`; `unit/pricing/test_money_characterization.py::test_missing_exponent_is_an_error_not_a_default` |
| Corrective 2: edit a rate in the admin screen, next purchase uses it | admin-006, pricing-013 | Admin rate path writes rate and history in one step; frozen quotes keep their price | `app/admin/service.py` (`set_rate`), `app/admin/postgres.py` | `unit/admin/test_service.py::test_admin_can_update_a_rate_and_it_records_who`; `integration/test_rate_edit_purchase.py::test_next_purchase_uses_the_edited_jpy_rate_and_history_is_written` (PostgreSQL), `::test_held_price_stays_frozen_when_the_rate_is_edited_before_payment` (PostgreSQL) |
| Corrective 4 and "1.2 stays live": no promotion until the corrective tests are green | system-017 | ADR-009 decision 1; CI fails on any skipped test | `.github/workflows/ci.yml`, `scripts/fail_on_skips.py` | `test_project_process.py::test_ci_fails_on_skipped_tests_and_checks_the_migration_round_trip`, `::test_fail_on_skips_script` |
| "Keep every release restorable" | system-018 | ADR-009 decisions 2 and 3: tags `v1.2.0` / `v1.3.0`, rollback first, Alembic downgrade caveat | `docs/runbooks/release-and-rollback.md`, `/healthz` version and `alembic_head` | `test_main_program.py::test_healthz_reports_version_and_alembic_head_unknown_when_db_down`, `::test_healthz_reads_alembic_head_when_db_is_up`, `::test_release_version_is_1_3_0` |
| Out-of-range order alert with a human on the end | audit-009 | ADR-009 decision 5: scheduled `check-orders`, 50% to 200% of base price per ticket (USD equivalent), one message through a notification port | `app/audit/anomaly.py`, `app/config/commands.py` (`check-orders`), `.github/workflows/order-watch.yml` | `unit/audit/test_anomaly.py::test_incident_one_percent_of_price_is_flagged`, `::test_boundaries_50_and_200_percent_are_inclusive_of_the_normal_band`, `::test_legitimate_jpy_order_is_not_a_false_alarm`, `::test_jpy_charged_one_percent_is_flagged`; `integration/test_order_watch.py` (PostgreSQL) |
| Backup owner | system-019 | ADR-009 decision 6: named owner, nightly `pg_dump`, restore drill | `scripts/backup.sh`, `scripts/restore.sh`, `docs/runbooks/backup-restore.md` | `test_project_process.py::test_backup_and_restore_scripts_refuse_without_database_url_and_never_print_it` (scripts only; no drill run, owner `[OPEN]`) |
| Localization: Spanish, more languages later | system-020 | ADR-010 decisions 1 and 2: one message catalog per language | `app/i18n/catalog.py`, `app/i18n/en.json`, `app/i18n/es.json`, `app/i18n/locales.py` | `unit/i18n/test_i18n.py::test_resolution_order_and_fallback`, `::test_catalogs_have_identical_keys_and_placeholders`, `::test_translate_fills_named_slots_and_falls_back`, `::test_lang_query_sets_cookie_and_translates` |
| Localization: dates in the reader's regional format | system-021 (also noted in catalog and orders) | ADR-010 decision 3 | `app/i18n/formatting.py` | `unit/i18n/test_i18n.py::test_dates_per_locale` |
| Localization: money as that currency is written | system-022 (also noted in catalog and orders) | ADR-010 decision 4 on top of ADR-008: locale decides separators and symbol placement, the minor unit decides decimals | `app/i18n/formatting.py`, `app/pricing/presenter.py` | `unit/i18n/test_i18n.py::test_money_per_locale`, `::test_locale_never_changes_the_amount` |
| The yen test stays green through localization | system-023, system-016 | ADR-010 decision 6: first gate | same code as above | `unit/i18n/test_yen_under_localization.py::test_yen_has_no_decimals_and_keeps_its_amount_in_every_locale`, `::test_english_locale_equals_the_unlocalized_formatter`; `unit/i18n/test_i18n.py::test_same_underlying_amounts_in_every_locale` |
| Extra: rate edits are recorded | pricing-013, admin-006 | New table `exchange_rate_history` (who, old, new, when) | `migrations/versions/0007_rate_history.py`, `app/admin/postgres.py` | `integration/test_rate_edit_purchase.py::test_next_purchase_uses_the_edited_jpy_rate_and_history_is_written` (PostgreSQL); `::test_database_rejects_a_zero_rate_even_via_direct_sql` (PostgreSQL) |
| Extra: delta guard on rate edits (more than 25% needs confirmation) | admin-006, pricing-013 | ADR-009 decision 4 | `app/admin/service.py` (`MAX_CHANGE`) | `unit/admin/test_service.py::test_large_change_is_rejected_without_confirmation`, `::test_large_change_is_accepted_with_confirmation_and_exact_25_percent_passes`, `::test_first_rate_for_a_currency_needs_no_confirmation`; `integration/test_rate_edit_purchase.py::test_ten_times_typo_is_refused_unless_confirmed` (PostgreSQL) |
| Extra: locale allowlist (a request cannot select files or inject text) | system-020 | ADR-010 decision 2 | `app/i18n/locales.py` | `unit/i18n/test_i18n.py::test_hostile_values_never_leave_the_allowlist`, `::test_oversized_accept_language_is_ignored_past_the_cap`, `::test_bad_lang_is_ignored_and_never_reflected` |
| Extra: no personal data in alerts | audit-009 | ADR-009 decision 5 | `app/audit/anomaly.py` (`Finding`, `notify`) | `unit/audit/test_anomaly.py::test_find_anomalies_returns_only_flagged_orders_without_pii`, `::test_notify_logs_at_error_without_pii`; `integration/test_order_watch.py` (PostgreSQL) |

## 2. What changed in the modeling

`workspace.dsl` has new elements and views, all tagged `PostCall6`. The earlier views exclude that tag, so the Call 3 and Call 5 diagrams stay as they were.

- **New component "Localization"** (`localization`) in the web app: message catalogs, locale resolution, `format_date()` and `format_money()`. Catalog, Orders and Purchase call it for dates and money. It asks Pricing for `minor_unit(currency)`, so the number of decimals still has one source. The buyer reaches it by choosing a language (`?lang`).
- **New component "Order monitor"** (`orderMonitor`): run by the scheduled `check-orders` command. It reads orders and event base prices from the database and calls the alert channel.
- **New external system "Alert channel"** (`alertChannel`): the message channel to a human, behind a notification port. The payload carries no personal data. Which channel it is stays `[OPEN]`.
- **New views:** `Container_PostCall6` and `Component_PostCall6`.

**Diagram images are not exported yet.** The `.png` files in `diagrams/` stop at `Container_PostCall5` and `Component_PostCall5`. The two PostCall6 views exist only in `workspace.dsl`. To finish, export `Container_PostCall6` and `Component_PostCall6` from Structurizr (names `structurizr-1-Container_PostCall6.png` and `structurizr-1-Component_PostCall6.png`) and check that they open without errors.

## 3. Why each change, in plain language

1. **Money formatting (pricing-014).** The incident came from one rule, "two decimals everywhere", that was wrong for one currency. The cure is not a better number but making it impossible to guess: the decimals come from the currency, and if the currency does not say, the code stops instead of assuming 2. A guessed default is how 4,500 yen became 45.
2. **A purchase test for every currency (system-016).** Our tests checked dollars, euros and pounds, and every check assumed two decimals. A test that buys in each currency and compares an exact total, with a second test that fails when a currency has no expectation, makes "we forgot yen" fail the build instead of reaching students.
3. **Admin rate path tested (admin-006, pricing-013).** Editing a rate is a production action that moves money, and no test exercised it. The test now edits a rate and checks the next purchase uses it, and that a purchase already on hold keeps its frozen price.
4. **History and the 25% guard.** The audit log recorded orders but not who changed a rate. A record of who, old and new rate, and when, plus a confirmation step for large moves, catches a ten-times typo before it is live. The guard is a speed bump, not a ban: an intended large change is allowed once confirmed.
5. **No promotion until green, no silent skips (system-017).** Marcus wanted a hot fix. A green gate that also fails on skipped tests means a missing database or browser cannot turn a failure into a quiet pass.
6. **Restorable releases (system-018).** Rollback in eleven minutes worked because the old version existed and the switch had been done before. Tags and a written switch-back make that repeatable, and the Alembic downgrade caveat stops a rollback from damaging data.
7. **Order alert (audit-009).** The log was perfect and nobody watched it. A scheduled check that flags a per-ticket total below 50% or above 200% of the base price, and sends one message, turns "found out from a group chat" into "found out from the system". No personal data goes into the message because the message leaves the database.
8. **Backup owner (system-019).** "I assumed the hosting side does it" is not a backup plan. The requirement is a named person, a nightly dump, and a restore drill, because a backup nobody has restored is unproven.
9. **Localization (system-020, 021, 022, 023).** Darnell's students need Spanish, dates and money in their own conventions. Message catalogs mean a new language is a new file. The locale comes from an allowlist, so a request cannot pick arbitrary files. Localization only changes how things are shown, never the stored amount, and the yen test must stay green, so the feature cannot reintroduce the incident.

## 4. Decisions taken and items left open

| Item | Status |
|---|---|
| Alert thresholds: below 50% or above 200% of base price per ticket | `[TEMPORARY_MVP_DEFAULT]` until the customer confirms |
| Rate-change confirmation above 25% | `[TEMPORARY_MVP_DEFAULT]` |
| Spanish wording (neutral Latin American `es`) | `[TEMPORARY_MVP_DEFAULT]` until a native speaker reviews it |
| Database backup owner | `[OPEN]`: Adaeze to name a person (due Friday). Until then system-019 is not satisfied |
| Alert recipient and channel | `[OPEN]`: who receives it, and the channel behind the port |
| JPY offered to real buyers | `[OPEN]`: customer sign-off. JPY is seeded for testing only |
| Spanish native-speaker review | `[OPEN]` |
| Who may decide a rollback | `[OPEN]`: the runbook says to restore first, but does not name the person who decides |
| Backup retention and tolerable data loss (24 h today) | `[OPEN]` |

## 5. What we decided not to change

| Raised or tempting | Decision |
|---|---|
| An on-call rotation for the alert | Explicitly deferred by Priya. We send one message to a human and leave the rotation `[OPEN]`. |
| Splitting `purchase/service.py`, `web/__init__.py` and `wiring.py` into smaller files | Deferred to the maintainability work in Deliverable 2. They are not needed for the Call 6 behaviour, and splitting them in the same change as the money fix would make the change harder to review. |
| Fixing the hot-fix as "one line" | The one-line fix was not the point; the standing rule is rollback first, then a reviewed fix. |
| More languages and right-to-left support | Not part of ADR-010. Adding a language is adding a catalog. |
| Hosting-side backup assumed | Not assumed. We do not rely on it. |

**Found in review and fixed.** The release runbook said `v1.3.0` adds no migration, but `migrations/versions/0007_rate_history.py` creates `exchange_rate_history`. The runbook now says migration `0007` is additive (v1.2.0 code runs against the v1.3.0 schema, so roll back code only) and that `alembic downgrade 0006` drops the history table.

## 6. Acceptance matrix

`docs/acceptance-matrix.md` lists the Call 6 rows as `OPEN`, by design, until the merged test run is green. Do not move a row to `PASS` until the GitHub Actions run (below) has shown its named proof green.

## 7. Verification status

**Run on the development machine** (from this worktree, `python -m pytest -q -p no:cacheprovider`):

- Result: **383 passed, 39 skipped, 87 deselected**. The 87 deselected are the Selenium system tests, which the default run excludes. The 39 skipped are PostgreSQL integration tests that need `EVENTHUB_TEST_DATABASE_URL`.
- This covers the unit, contract and process tests, including every non-PostgreSQL test named in section 1.

**Not run, and therefore not claimed as passed:**

- **PostgreSQL integration tests** (including the per-currency purchase test, the rate-edit purchase test, the order-watch query test and the migration round trip). There is no Docker or PostgreSQL on the development machine.
- **Selenium system tests.** Not run for this deliverable.
- **Restore drill and notification delivery.** Not run; there is no backup owner and no real alert channel.
- **Spanish text.** Checked for matching keys only, not for correctness by a native speaker.

These are to be proven by the GitHub Actions run, which has PostgreSQL and a browser and fails on any skipped test. Until that run is green, the rows in section 1 that cite PostgreSQL tests are planned proof, not passed proof.
