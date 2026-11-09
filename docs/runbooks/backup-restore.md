# Runbook: database backup and restore (system-019)

Database: PostgreSQL 16. Status: scripts written and syntax-checked; **never run against a real
database** and no backup schedule is live yet.

**Owner:** [OPEN] no person named. A backup without an owner is not a backup; name one before go-live.

## Backup

- Command: `EVENTHUB_DATABASE_URL=... scripts/backup.sh` writes `backups/eventhub-<UTC stamp>.dump`
  (`pg_dump --format=custom`). It refuses to run without the variable and never prints it.
- Schedule: nightly, off-peak (for example 02:00 UTC), run by the owner's scheduler (cron or the
  hosting platform's job runner), plus one manual run before every release.
- The orders table holds money records, so a nightly loss window of up to 24 hours is the current
  accepted risk. [OPEN] confirm with the business, or add WAL archiving / point-in-time recovery.

## Dumps contain personal data

Accounts (names, e-mail addresses, password hashes) and orders are in every dump.

- Encrypt before leaving the host (for example `gpg --symmetric` or storage-side encryption with
  customer-managed keys); never commit dumps (`backups/` is git-ignored).
- Store them in a location separate from the database server, readable only by the owner and one deputy.
- Retention: [OPEN] proposal 14 daily + 8 weekly copies, then delete. Delete restored copies after a drill.
- Do not load a production dump into a shared or developer environment.

## Restore

1. Stop writes (maintenance page or stop the app) if restoring production.
2. Decrypt the chosen dump.
3. `EVENTHUB_DATABASE_URL=<target> scripts/restore.sh backups/eventhub-<stamp>.dump`
   (drops and recreates objects in the target database).
4. Start the app and check `GET /healthz`: `alembic_head` matches the release you run.
5. Spot-check: latest order exists, `eventhub check-orders` reports nothing unexpected.

## Restore drill (do before go-live, then every quarter)

1. Back up a test database, restore into a **scratch** database (never the original).
2. Run the app against it, check `/healthz` and an order page.
3. Record date, dump size, restore time and who did it below. Delete the scratch database.

| Date | Who | Dump size | Restore time | Result |
|---|---|---|---|---|
| (no drill done yet) | | | | |
