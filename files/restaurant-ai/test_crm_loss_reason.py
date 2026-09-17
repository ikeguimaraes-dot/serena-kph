"""Offline model/API authorization checks. No Twilio, DB, email or network calls."""
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import ValidationError
from models import ContactKanbanMove, ContactUpdate, ContactUpsert
from crm_stages import MOTIVOS_PERDA

with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-only", "ADMIN_SECRET": "test-secret"}):
    import main

OPERATOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
HEADERS = {"x-admin-secret": "test-secret", "x-operator-id": OPERATOR}


class ContractTest(unittest.TestCase):
    def test_every_loss_reason_is_valid_and_other_requires_detail(self):
        for reason in MOTIVOS_PERDA:
            model = ContactKanbanMove(estagio_kanban="perdido", motivo_perda=reason,
                                      motivo_perda_detalhe=" motivo documentado " if reason == "outro" else None)
            self.assertEqual(model.motivo_perda, reason)
        for payload in ({"estagio_kanban": "perdido"},
                        {"estagio_kanban": "perdido", "motivo_perda": "outro", "motivo_perda_detalhe": " "},
                        {"estagio_kanban": "perdido", "motivo_perda": "inventado"},
                        {"estagio_kanban": "qualificado", "motivo_perda": "preco"}):
            for model in (ContactUpdate, ContactUpsert, ContactKanbanMove):
                with self.subTest(model=model.__name__, payload=payload), self.assertRaises(ValidationError):
                    model(**({"celular": "synthetic"} if model is ContactUpsert else {}), **payload)

    def test_normal_profile_edit_and_nonloss_stage_remain_compatible(self):
        self.assertIsNone(ContactUpdate(nome="Test").motivo_perda)
        self.assertEqual(ContactKanbanMove(estagio_kanban="proposta").estagio_kanban, "proposta")


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patches = [patch.dict(os.environ, {"ADMIN_SECRET": "test-secret"}),
            patch("api_access.operator_profile", new_callable=AsyncMock,
                  return_value={"id": OPERATOR, "role": "atendente", "restaurante_id": "first"}),
            patch("main.db.update_contact", new_callable=AsyncMock, return_value={"id": 1}),
            patch("main.db.upsert_contact", new_callable=AsyncMock, return_value={"id": 1}),
            patch("main.db.move_contact_kanban", new_callable=AsyncMock, return_value={"id": 1}),
            patch("main.notif.send_to_customer")]
        self.active = [p.start() for p in self.patches]
        self.update, self.upsert, self.move = self.active[2:5]
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://local")

    async def asyncTearDown(self):
        await self.client.aclose()
        for p in reversed(self.patches):
            p.stop()

    async def test_missing_reason_is_422_for_all_three_writers(self):
        for method, url, payload in (
            ("PATCH", "/api/contacts/test?rid=first", {"estagio_kanban": "perdido"}),
            ("PATCH", "/api/contacts/test/kanban?rid=first", {"estagio_kanban": "perdido"}),
            ("POST", "/api/contacts?rid=first", {"celular": "test", "estagio_kanban": "perdido"})):
            response = await self.client.request(method, url, json=payload, headers=HEADERS)
            self.assertEqual(response.status_code, 422, response.text)
        for mock in (self.update, self.upsert, self.move):
            mock.assert_not_awaited()

    async def test_generic_patch_uses_validated_actor_and_tenant(self):
        payload = {"estagio_kanban": "perdido", "motivo_perda": "outro", "motivo_perda_detalhe": " Data mudou "}
        response = await self.client.patch("/api/contacts/test?rid=first", json=payload, headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        self.update.assert_awaited_once_with("test", {**payload, "motivo_perda_detalhe": "Data mudou"},
                                           restaurant_id="first", operator_id=OPERATOR)

    async def test_upsert_and_kanban_propagate_reason_and_actor(self):
        payload = {"estagio_kanban": "perdido", "motivo_perda": "preco"}
        response = await self.client.post("/api/contacts?rid=first", json={"celular": "test", **payload}, headers=HEADERS)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.upsert.await_args.kwargs, {"restaurant_id": "first", "operator_id": OPERATOR})
        self.assertEqual(self.upsert.await_args.args[0]["motivo_perda"], "preco")
        response = await self.client.patch("/api/contacts/test/kanban?rid=first", json=payload, headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.move.await_args.kwargs["motivo_perda"], "preco")
        self.assertEqual(self.move.await_args.kwargs["operator_id"], OPERATOR)

    async def test_unauthenticated_and_other_tenant_cannot_write_loss(self):
        payload = {"estagio_kanban": "perdido", "motivo_perda": "preco"}
        r = await self.client.patch("/api/contacts/test/kanban?rid=first", json=payload)
        self.assertEqual(r.status_code, 401)
        r = await self.client.patch("/api/contacts/test/kanban?rid=second", json=payload, headers=HEADERS)
        self.assertEqual(r.status_code, 403)
        self.move.assert_not_awaited()

    async def test_history_requires_auth_and_scopes_phone(self):
        with patch("main.db.get_contact", new_callable=AsyncMock, return_value={"id": 1}) as contact, \
             patch("main.db.get_contact_stage_history", new_callable=AsyncMock, return_value=[]) as history:
            r = await self.client.get("/api/contacts/test/kanban/history?rid=first")
            self.assertEqual(r.status_code, 401)
            contact.assert_not_awaited()
            r = await self.client.get("/api/contacts/test/kanban/history?rid=second", headers=HEADERS)
            self.assertEqual(r.status_code, 403)
            r = await self.client.get("/api/contacts/test/kanban/history?rid=first", headers=HEADERS)
            self.assertEqual(r.status_code, 200)
            history.assert_awaited_once_with("test", "first", limit=100)

    async def test_mark_inactive_is_explicit_nonmutating_compatibility_response(self):
        with patch("main.db.mark_inactive_contacts", new_callable=AsyncMock) as mutate:
            r = await self.client.post("/api/contacts/mark-inactive", headers={"x-admin-secret": "test-secret"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["deprecated"])
            self.assertEqual(r.json()["updated"], 0)
            mutate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
