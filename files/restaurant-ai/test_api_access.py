"""Local authorization contract. Database, Twilio and auth identities are mocked."""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-only", "ADMIN_SECRET": "test-secret"}):
    import main
import api_access
import database as db
import agent_context
import tools

OPERATOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
HEADERS = {"x-admin-secret": "test-secret", "x-operator-id": OPERATOR}


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = []
        def mock(target, *args, **kwargs):
            p = patch(target, *args, **kwargs)
            self.stack.append(p)
            return p.start()
        self.mock = mock
        p = patch.dict(os.environ, {"ADMIN_SECRET": "test-secret"})
        p.start(); self.stack.append(p)
        self.profile = mock("api_access.operator_profile", new_callable=AsyncMock,
                            return_value={"id": OPERATOR, "role": "atendente", "restaurante_id": "first"})
        self.owner = mock("api_access.resource_tenant", new_callable=AsyncMock, return_value="first")
        self.send = mock("main.notif.send_to_customer")
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://local")

    async def asyncTearDown(self):
        await self.client.aclose()
        for p in reversed(self.stack): p.stop()

    async def test_anonymous_private_reads_and_writes_never_reach_side_effects(self):
        cases = [
            ("POST", "/api/handoff/1/reply", {"mensagem": "test", "atendente_nome": "test"}),
            ("POST", "/api/handoff/1/assume", {"atendente_nome": "test"}),
            ("POST", "/api/handoff/1/resolve", {"atendente_nome": "test"}),
            ("POST", "/api/handoff/assumir", {"user_phone": "+test", "restaurant_id": "first"}),
            ("PATCH", "/api/handoff/1/kanban", {"stage": "resolvido"}),
            ("PATCH", "/api/contacts/test?rid=first", {"nome": "test"}),
            ("POST", "/api/contacts?rid=first", {"celular": "test"}),
            ("POST", "/api/contacts/test/retag?restaurant_id=first", {}),
            ("GET", "/api/agenda/first/reservas", None),
            ("GET", "/api/restaurants/first/team", None),
            ("GET", "/api/restaurants/first/conversations", None),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                r = await self.client.request(method, path, json=body)
                self.assertEqual(r.status_code, 401, r.text)
        self.owner.assert_not_awaited()
        self.send.assert_not_called()

    async def test_spoofed_operator_without_service_secret_is_rejected(self):
        r = await self.client.get("/api/restaurants", headers={"x-operator-id": OPERATOR})
        self.assertEqual(r.status_code, 401)
        self.profile.assert_not_awaited()

    async def test_scoped_operator_sees_only_assigned_restaurant(self):
        self.mock("main.db.get_all_restaurants", new_callable=AsyncMock,
                  return_value=[{"id": "first"}, {"id": "second"}])
        r = await self.client.get("/api/restaurants", headers=HEADERS)
        self.assertEqual(r.json(), [{"id": "first"}])

    async def test_authorized_handoff_and_cross_tenant_denial(self):
        get = self.mock("main.db.get_handoff_by_id", new_callable=AsyncMock,
                        return_value={"user_phone": "+synthetic", "restaurant_id": "first"})
        update = self.mock("main.db.update_handoff_status", new_callable=AsyncMock, return_value=True)
        r = await self.client.post("/api/handoff/1/assume", headers=HEADERS, json={"atendente_nome": "Vic"})
        self.assertEqual(r.status_code, 200, r.text)
        update.assert_awaited_once()
        get.reset_mock(); update.reset_mock()
        self.owner.return_value = "second"
        r = await self.client.post("/api/handoff/2/assume", headers=HEADERS, json={"atendente_nome": "Vic"})
        self.assertEqual(r.status_code, 403)
        get.assert_not_awaited(); update.assert_not_awaited()

    async def test_crm_update_propagates_tenant_and_blocks_other_business(self):
        update = self.mock("main.db.update_contact", new_callable=AsyncMock, return_value={"nome": "test"})
        r = await self.client.patch("/api/contacts/test?rid=first", headers=HEADERS, json={"nome": "test"})
        self.assertEqual(r.status_code, 200, r.text)
        update.assert_awaited_once_with("test", {"nome": "test"}, restaurant_id="first")
        update.reset_mock()
        r = await self.client.patch("/api/contacts/test?rid=second", headers=HEADERS, json={"nome": "test"})
        self.assertEqual(r.status_code, 403)
        update.assert_not_awaited()

    async def test_unknown_operator_denied_and_legacy_group_scope_preserved(self):
        self.profile.return_value = None
        r = await self.client.get("/api/restaurants", headers=HEADERS)
        self.assertEqual(r.status_code, 403)
        rows = [{"id": "first"}, {"id": "second"}]
        self.mock("main.db.get_all_restaurants", new_callable=AsyncMock, return_value=rows)
        for role in ("admin", "atendente"):
            self.profile.return_value = {"role": role, "restaurante_id": None}
            r = await self.client.get("/api/restaurants", headers=HEADERS)
            self.assertEqual(r.json(), rows)

    async def test_groupwide_staff_cannot_change_team_or_admin_prompts(self):
        self.profile.return_value = {"role": "atendente", "restaurante_id": None}
        r = await self.client.post("/api/restaurants/first/team", headers=HEADERS,
                                   json={"nome": "test", "role": "gerente", "whatsapp": "+test"})
        self.assertEqual(r.status_code, 403, r.text)
        r = await self.client.get("/api/serena/prompts", headers=HEADERS)
        self.assertEqual(r.status_code, 403)

    async def test_conflicting_tenant_parameters_cannot_bypass_retag_scope(self):
        r = await self.client.post("/api/contacts/test/retag?rid=first&restaurant_id=second", headers=HEADERS)
        self.assertEqual(r.status_code, 403)

    async def test_scoped_admin_cannot_use_query_string_to_unlock_global_data(self):
        self.profile.return_value = {"role": "admin", "restaurante_id": "first"}
        r = await self.client.get("/api/serena/recent?rid=first", headers=HEADERS)
        self.assertEqual(r.status_code, 403)

    async def test_resource_id_must_belong_to_the_path_tenant(self):
        self.owner.return_value = "second"
        r = await self.client.patch("/api/agenda/first/reservas/other/confirmar", headers=HEADERS)
        self.assertEqual(r.status_code, 404)

    async def test_auth_database_outage_fails_closed(self):
        self.profile.side_effect = RuntimeError("do not expose database internals")
        r = await self.client.get("/api/restaurants", headers=HEADERS)
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("internals", r.text)

    async def test_service_secret_remains_usable_without_operator(self):
        self.mock("main.db.get_team", new_callable=AsyncMock, return_value=[])
        r = await self.client.get("/api/restaurants/first/team", headers={"x-admin-secret": "test-secret"})
        self.assertEqual(r.status_code, 200, r.text)
        self.profile.assert_not_awaited()

    async def test_availability_stays_public_but_reservation_data_does_not(self):
        self.mock("main.db.get_disponibilidade_semana", new_callable=AsyncMock, return_value=[])
        r = await self.client.get("/api/agenda/first/disponibilidade?data=2026-10-01")
        self.assertEqual(r.status_code, 200, r.text)
        r = await self.client.get("/api/agenda/first/reservas/one")
        self.assertEqual(r.status_code, 401)

    async def test_widget_and_webhook_contracts_remain_explicit(self):
        self.assertIn(("POST", "/api/widget/reserva/{restaurant_id}"), api_access.PUBLIC_ROUTES)
        webhook = next(r for r in main.app.routes if getattr(r, "path", "") == "/webhook/whatsapp")
        self.assertTrue(any(d.call == main.validate_twilio_signature for d in webhook.dependant.dependencies))


class AgentTenantTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_context_reads_only_current_tenant(self):
        with patch.object(db, "get_contact", new_callable=AsyncMock, return_value={"nome": "First"}) as contact, \
             patch.object(db, "get_contact_reservations", new_callable=AsyncMock, return_value=[]) as reservations:
            result = await agent_context.build_contact_context("+synthetic", "first")
        self.assertIn("First", result)
        contact.assert_awaited_once_with("+synthetic", restaurant_id="first")
        reservations.assert_awaited_once_with("+synthetic", limit=10, restaurant_id="first")

    async def test_tool_writes_only_current_tenant(self):
        with patch.object(db, "get_contact", new_callable=AsyncMock, return_value={}) as contact, \
             patch.object(db, "upsert_contact", new_callable=AsyncMock) as write:
            await tools.update_contact("+synthetic", "first", nome="First")
        contact.assert_awaited_once_with("+synthetic", restaurant_id="first")
        write.assert_awaited_once_with({"celular": "+synthetic", "nome": "First"}, restaurant_id="first")


if __name__ == "__main__":
    unittest.main()
