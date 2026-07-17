# Yummy incident response and disaster recovery

## Targets

- **RPO:** 24 hours until PITR is enabled; 15 minutes with verified Supabase PITR.
- **RTO:** 4 hours for database restore; 30 minutes for stateless app rollback.
- Backups are valid only after a successful restore drill to a separate database.

## Severity

- SEV-1: payment/PII compromise, production DB unavailable, forged webhook accepted.
- SEV-2: email/Redis/worker outage, elevated 5xx, reconciliation backlog.
- SEV-3: isolated partner/customer issue without data or money risk.

## First response

1. Preserve evidence and timestamps; do not delete logs/events.
2. Disable affected checkout/provider (`YUMMY_PAYMENT_MODE=disabled`).
3. Rotate compromised secrets and revoke sessions.
4. Block affected accounts/payment accounts.
5. Notify owner/legal contacts according to Kazakhstan obligations.
6. Record timeline, scope, root cause and regression tests.

## Database recovery

1. Never restore over production directly.
2. Select encrypted backup and verify SHA-256.
3. Set a dedicated empty `RESTORE_DATABASE_URL`.
4. Run `deploy/restore-drill.sh backup.dump.age`.
5. Validate Alembic revision, row counts, payments/ledger consistency and app smoke tests.
6. Promote restored DB only through an approved cutover plan.

## Payment incident

- Treat redirect/browser status as untrusted.
- Reconcile provider IDs, amount, currency, merchant and event signature.
- Do not retry refund/payment manually without the same idempotency key.
- Disable a partner payment account on mismatch and create a critical audit event.

## Required drills

- Monthly encrypted backup creation check.
- Quarterly clean-room restore drill.
- Quarterly secret rotation/tabletop exercise.
- Annual external security/payment review before peak traffic.
