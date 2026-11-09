# Runbook: release and rollback (system-017)

Status: draft. EventHub has never been deployed to a production environment, so the switch-back
below has **not been rehearsed** and no rollback time is claimed. Rehearse it before the first
real release and record the measured time here.

## Tags

| Tag | Meaning |
|---|---|
| `v1.2.0` | Baseline: the last release before this maintenance work. Always kept runnable. |
| `v1.3.0` | Maintenance release (order-total check, `/healthz` version info, backup, CI gates). |

`pyproject.toml` carries the same version; `/healthz` reports it as `version`, together with
`alembic_head` (the database schema revision, or `unknown` when the database is unreachable).

## Roll back first, investigate second

1. Decide to roll back (see "Who may trigger"). Do not debug in production first.
2. Check compatibility (below).
3. Redeploy the previous tag: `git checkout v1.2.0`, install (`pip install -e .`) and start the
   app exactly as the new release was started. Nothing else changes.
4. Confirm: `GET /healthz` shows `"version": "1.2.0"` and an `alembic_head` the old code supports.
5. Write down what happened; fix forward in a new release (`v1.3.1`), not by editing a tag.

## Database schema and the downgrade caveat

Migrations `0001` to `0006` all have `downgrade()`, and CI checks `downgrade -1` then
`upgrade head` on every change. But a downgrade can drop columns or tables **and their data**.

- Prefer rolling back the code only, when the older code still works with the newer schema
  (additive migrations only). Compare `alembic_head` from `/healthz` with the head the old tag
  expects (`git show v1.2.0:migrations/versions` lists its migrations).
- If the old code needs an older schema, take a backup first (`scripts/backup.sh`, see
  `backup-restore.md`), then `alembic downgrade <revision>` for exactly the extra migrations.
- v1.3.0 adds no migration, so v1.2.0 and v1.3.0 are schema-compatible. A future release that
  adds a migration must state its compatibility in its release notes.

## Before every release

- CI is green with **zero skipped tests** (`scripts/fail_on_skips.py`) and the migration round-trip passed.
- A fresh backup exists.
- The corrective tests for the incident being fixed are green. A release does not go out otherwise.

## Who may trigger

[OPEN] Role not decided (candidates: release manager or on-call developer). Until a person or role
is named, nobody is authorised and the team lead decides case by case.
