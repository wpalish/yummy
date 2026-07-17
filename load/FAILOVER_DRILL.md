# PostgreSQL failover / pool saturation drill

Run only against a dedicated staging Supabase project.

1. Set `TARGET_ENV=staging`, start normal catalog k6 load, record p95/p99 and errors.
2. Observe `/admin/system/database`: pool size/available/waiting and connection errors.
3. Pause/restart the staging database using the provider-supported control; never kill production.
4. Verify `/health` returns 503 while `/live` remains 200.
5. Verify requests fail bounded by pool/statement timeout, not hang indefinitely.
6. Restore DB and verify pool reconnects, `/health` becomes 200 and no transaction remains idle.
7. Run reconciliation and assert no duplicate paid orders, commission entries or inventory loss.
8. Record detection time, recovery time, max errors, RPO/RTO and corrective actions.

Acceptance: no oversell, no duplicate webhook fulfillment, no silent writes lost, recovery within agreed RTO.
