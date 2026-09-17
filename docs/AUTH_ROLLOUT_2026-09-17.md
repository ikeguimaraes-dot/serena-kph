# Panel authorization and CRM isolation — 17 September 2026

## Contract

- The Next proxy validates the Supabase user with `getUser()`. Anonymous and
  invalid sessions never receive the server credential. Refreshed cookies are
  returned, and responses are private/no-store.
- Backend `/api/*` routes require `ADMIN_SECRET`. The proxy also sends the
  authenticated user ID. Backend reads role and scope from `operadores`; neither
  user metadata nor browser headers establish authorization.
- A secret-only call remains a trusted service/admin integration. Keep the
  secret server-side. An unknown operator is denied, not treated as a service.
- Current Ike (admin) and Vic (atendente) have `restaurante_id=NULL`, the existing
  server-assigned groupwide scope. They can continue selecting the group's units.
  A non-null scope limits an operator to that business. Null is not a self-serve
  default; operator creation/assignment must remain administrative.
- Atendentes access operational reservations, OS, conversations, handoffs and
  scoped CRM. Menu/configuration reads remain available; team/menu/configuration
  mutations and management reports/prompts require admin.
- Contact requests carry `rid` (selected unit). Contact writes, reads, NPS
  lookups, search and statistics use the tenant. Agent context/tools propagate
  the same tenant. A phone alone no longer selects or modifies a CRM profile.
- Explicit anonymous exceptions: GET agenda availability, POST reservation
  widget. Health and Twilio/Stripe webhooks retain their existing contracts.

## Deployment order

1. Deploy the companion frontend branch from its isolated worktree, linked to
   the existing `madonna-painel` project. Preserve the existing Vercel production
   variables (`BACKEND_URL`, `ADMIN_SECRET`, `NEXT_PUBLIC_SUPABASE_URL`,
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`). Vercel applies them at build/runtime; there
   is no need to export their values or copy `.env` files.
2. Verify anonymous `/api/contacts` is 401 and login still opens. With existing
   operator sessions, verify unit selection and read-only conversation/CRM APIs.
3. Deploy the backend commit together with the rest of the tested release.
   No schema change, environment change or multi-tenant flag activation needed.
4. Verify direct anonymous private API requests are 401, valid service requests
   still work, and public availability/widget validation remain available.
   Do not send live WhatsApp replies as an automatic smoke test.

Deploying backend first would temporarily require `rid` before old panel clients
send it. Reload long-lived panel tabs after release. Integrations calling private
APIs without a credential must adopt the service credential; contact calls must
also name their unit. The public widget endpoint is unchanged.

## Validation

- 43 local backend tests: API authorization, tenant scope, agent CRM context,
  catalogue safety and existing handoff routing. External calls mocked.
- `test_crm_tenancy_contract.py`: passed against current schema with two
  synthetic tenants, always rolled back; no existing customer records read and
  no messages sent.
- Companion frontend: six proxy contract tests and successful Next 16 build.
- No production environment changes or deployments performed by this package.

This is not a complete application security audit. Service credentials still
grant administrative access; additional independent modules and database routines
need review as they are brought into the multi-tenant product.
