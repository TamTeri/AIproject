# ADR-004: How an account becomes an administrator

**Status:** `[OPEN]`. The customer has not decided. A temporary default is in use.

## Temporary default `[TEMPORARY_MVP_DEFAULT]`
Administrators are created or promoted only by an operator on the server:

```bash
EVENTHUB_ADMIN_EMAIL=admin@example.com EVENTHUB_ADMIN_PASSWORD='...' \
  python -m app.db.commands create-admin
```

The website has no self-service promotion and no "make admin" button.

## Still open
Who may be an administrator, how admins are removed, whether admins need two-factor login, and how often access is reviewed.
