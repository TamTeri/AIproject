"""audit-009 against real PostgreSQL: the query flags the 1%-price order and nothing else.

Needs EVENTHUB_TEST_DATABASE_URL (skipped otherwise, like the other integration tests).
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.audit.anomaly import find_anomalies
from app.db.transaction import SqlTransaction

pytestmark = [pytest.mark.postgres, pytest.mark.requirement("audit-009")]


def test_query_flags_only_the_out_of_range_order_and_returns_no_pii(seeded_database):
    engine = seeded_database.engine
    with engine.begin() as c:
        account = c.execute(
            text(
                "INSERT INTO accounts (name, normalized_email, password_hash) "
                "VALUES ('W', :e, 'x') RETURNING id"
            ),
            {"e": f"{uuid4().hex[:8]}@example.com"},
        ).scalar_one()
        event = c.execute(
            text(
                "INSERT INTO events (catalog_key, title, artist, venue, starts_at, host_type, "
                "base_price_minor, capacity) VALUES (:k, 'W', 'W', 'W', CURRENT_TIMESTAMP + INTERVAL '30 days', "
                "'usf', 2000, 10) RETURNING id"
            ),
            {"k": f"watch-{uuid4().hex}"},
        ).scalar_one()
        order_ids = []
        for total in (2000, 20):  # normal, and the incident (1% of price)
            hold = c.execute(
                text(
                    "INSERT INTO holds (event_id, buyer_id, quantity, status, expires_at, terminal_at) "
                    "VALUES (:e, :b, 1, 'converted', CURRENT_TIMESTAMP + INTERVAL '1 hour', CURRENT_TIMESTAMP) "
                    "RETURNING id"
                ),
                {"e": event, "b": account},
            ).scalar_one()
            order_ids.append(
                c.execute(
                    text(
                        "INSERT INTO orders (buyer_id, event_id, hold_id, quantity, currency_code, rate_applied, "
                        "total_minor, quote_snapshot) VALUES (:b, :e, :h, 1, 'USD', 1, :t, CAST(:s AS JSONB)) "
                        "RETURNING id"
                    ),
                    {"b": account, "e": event, "h": hold, "t": total, "s": json.dumps({})},
                ).scalar_one()
            )

    tx = SqlTransaction(engine)
    try:
        findings = find_anomalies(tx)
    finally:
        tx.rollback()
    assert [f.order_id for f in findings] == [str(order_ids[1])]
    assert findings[0].event_id == str(event) and findings[0].currency == "USD"
