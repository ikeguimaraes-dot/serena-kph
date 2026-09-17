# Public reservations — Sprint 5

## Contract

- Public page: `/reservar/{restaurant_id}`. Only this exact page boundary bypasses operator login; the existing widget stays unchanged.
- `GET /api/public/reservations/{restaurant_id}?date=YYYY-MM-DD&people=N`: public business facts, slot availability booleans, and `available`, `unavailable`, or `unconfigured`. It exposes no guest records, names, phone lookups, occupancy counts, or private notes.
- `POST` same path accepts name, phone, date, people, slot UUID and request UUID. `201` means an INSERT into `reservas` committed; `200` means replay of that request. Both return `status: pending`, the reference, date, time and party size. The page says “Reserva registrada; aguardando confirmação da equipe”. No outgoing messages or payments are triggered.
- `409`: capacity or schedule rule conflict. `422`: invalid data or cross-unit slot. `503`: unknown configuration, special event/payment flow, or temporary outage. An unknown schedule never becomes “lotado”.

## Database safety

`db.criar_reserva` delegates to one service shared with the agent and private panel. It validates São Paulo local date/time, configured booking window/lead time/same-day policy, active tenant slot and weekday, party limits, closures, special events and capacity.

Inside one READ COMMITTED transaction: acquire the tenant/request advisory lock (if idempotency applies), replay/check the request hash, acquire the tenant/date/slot advisory lock, re-read capacity, INSERT pending reservation and store the request result. Pending and confirmed bookings consume capacity. Reactivating a cancelled/completed booking uses the same slot lock and capacity check. Cancelling frees capacity. Advisory locks are transaction scoped and compatible with connection pooling.

Idempotency and limiter tables have RLS enabled with all PUBLIC/anon/authenticated privileges revoked. Access uses the existing backend PostgreSQL connection. Public responses are explicitly projected. A per-worker peer-IP coarse rate limit and an atomic database limit of five committed public requests per normalized phone/tenant/ten-minute bucket bound simple abuse. Replays do not consume another bucket count. This is not phone verification or a distributed edge WAF; rotated phone numbers can still generate requests. Old limiter buckets may be deleted after 24 hours; keep idempotency records to preserve replay guarantees.

## Compatibility / boundaries

- No live schedules or capacities are invented or seeded.
- Three official fallback booking links are source-recorded in `reservation_links.py`; Levvai uses its current DB phone when no evidenced booking link exists.
- `get_reservation_link` now receives the conversation's actual tenant and points to its public page. It no longer uses global RESTAURANT_ID.
- The agent previously announced and emailed “confirmed” while its INSERT defaulted to `pendente`. It now reports pending and leaves confirmation email to the existing staff-confirmation path.
- Payment/special-event reservations route to the team. No new payment or deposit logic is included.
- This prevents overbooking for writers using this application's `reservas` paths. External Tagme inventory, legacy `reservations`, and direct SQL writes are not synchronized by this patch; do not claim cross-provider capacity guarantees.
- The old public availability endpoint and old widget remain compatible; the new page uses the authoritative service.

## Validation

- 49 offline Python tests: public HTTP semantics/privacy/errors, auth/tenant contract, menu fallback, handoff regressions and correct-unit links.
- Real restored-schema SQL hook: last-place concurrent requests yield one INSERT/one conflict; concurrent same-key requests yield one INSERT/one replay; same key across tenants is independent; reactivation cannot bypass capacity; malformed date/phone/party, wrong tenant/weekday/time, missing config/slot, closures, payment/special-event rules and shared limiter reject appropriately. ACL/RLS checks deny client roles. All data lives only in the disposable local restore.
- Frontend: ten Node tests (proxy/auth/public boundary, double-click dedup, retry key reuse, no success on failure), Next 16 production build, and local HTTP SSR checks for available/unconfigured + factual JSON-LD.
- Browser visual QA could not run: CUA reported no available browser. No screenshot claim.

## Release order

1. Apply `supabase/migrations/20260917043836_public_reservation_idempotency.sql` after backup/review. It is additive and creates no schedules. Never grant its tables to public clients.
2. Deploy the frontend public route/allowlists. No new public environment variables or secrets are needed; existing server BACKEND_URL applies.
3. Deploy backend public router/service/tenant-aware link generation. This order ensures generated `/reservar/{rid}` links already resolve.
4. Read-only production checks: the four business pages and public GETs show correct identities and honest configuration state; private endpoints still reject anonymous calls. Do not create synthetic production bookings or send messages as a smoke check.

Rollback code if necessary; keep the additive idempotency tables and existing booking rows. Do not drop reservation/customer data to roll back a release.

References: [PostgreSQL advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS), [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).
