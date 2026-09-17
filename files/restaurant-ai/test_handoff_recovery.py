"""Offline handoff regression tests. Never opens DB connections or sends messages.

Run: python -m unittest test_handoff_recovery -v (Python 3.10+).
"""

import io
import json
import os
import unittest
from contextlib import asynccontextmanager, redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import database as db
import notifications as notif


class HandoffRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.restaurant = {
            "nome": "Instituto Levvai",
            "whatsapp_number": "+15550000001",
        }
        self.manager = {"whatsapp": "+15550000002"}
        self.lookup_error = False
        self.queries = []

        async def fetchrow(query, *args):
            self.queries.append((query, args))
            if "INSERT INTO handoff_sessions" in query:
                return {"id": 42}
            if self.lookup_error:
                raise RuntimeError("lookup unavailable")
            if "FROM restaurants" in query:
                return self.restaurant
            if "FROM team_members" in query:
                return self.manager
            raise AssertionError("Unexpected database query")

        self.connection = SimpleNamespace(fetchrow=AsyncMock(side_effect=fetchrow))

        @asynccontextmanager
        async def acquire():
            yield self.connection

        self.addCleanup(patch.stopall)
        patch.object(db, "pool", return_value=SimpleNamespace(acquire=acquire)).start()
        self.discord = patch.object(notif, "notify_handoff_discord", return_value=True).start()
        self.clinical = patch.object(notif, "notify_escalacao_gerente", return_value=True).start()
        self.stdout = io.StringIO()
        self.redirect = redirect_stdout(self.stdout)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    async def test_clinical_route_uses_levvai_manager_and_sender(self):
        result = await db.create_handoff("+15550000003", "levvai", "[LARA]: pós-procedimento")

        self.assertEqual(result, 42)
        self.discord.assert_called_once_with("Instituto Levvai", "+15550000003", "[LARA]: pós-procedimento")
        self.clinical.assert_called_once_with(
            from_number="+15550000001", gerente_whatsapp="+15550000002",
            customer_phone="+15550000003", motivo="[LARA]: pós-procedimento",
        )
        manager_query, params = next(q for q in self.queries if "FROM team_members" in q[0])
        self.assertEqual(params, ("levvai",))
        for restriction in ("restaurant_id=$1", "role='gerente'", "ativo=true", "NULLIF(TRIM(whatsapp), '')"):
            self.assertIn(restriction, manager_query)

    async def test_other_tenant_cannot_trigger_lara_route(self):
        self.assertEqual(await db.create_handoff("+15550000003", "meet_and_eat", "[LARA]: pedido"), 42)
        self.discord.assert_called_once()
        self.clinical.assert_not_called()
        self.assertFalse(any("FROM team_members" in q for q, _ in self.queries))

    async def test_ordinary_levvai_handoff_remains_discord_only(self):
        self.assertEqual(await db.create_handoff("+15550000003", "levvai", "Cliente quer atendente"), 42)
        self.discord.assert_called_once()
        self.clinical.assert_not_called()

    async def test_missing_manager_preserves_handoff_and_discord(self):
        self.manager = None
        self.assertEqual(await db.create_handoff("+15550000003", "levvai", "[LARA]: pedido"), 42)
        self.discord.assert_called_once()
        self.clinical.assert_not_called()
        self.assertIn("sem gerente ativo", self.stdout.getvalue())
        self.assertIn("Rota clínica pendente no painel", self.stdout.getvalue())

    async def test_twilio_failure_preserves_handoff_with_discord_fallback(self):
        self.clinical.return_value = False
        self.assertEqual(await db.create_handoff("+15550000003", "levvai", "[LARA]: pedido"), 42)
        self.assertIn("Discord aceitou=True", self.stdout.getvalue())

    async def test_discord_failure_does_not_prevent_clinical_attempt(self):
        self.discord.side_effect = RuntimeError("Discord unavailable")
        self.assertEqual(await db.create_handoff("+15550000003", "levvai", "[LARA]: pedido"), 42)
        self.clinical.assert_called_once()

    async def test_all_channels_fail_records_explicit_panel_fallback(self):
        self.discord.return_value = False
        self.clinical.side_effect = RuntimeError("Twilio unavailable")
        self.assertEqual(await db.create_handoff("+15550000003", "levvai", "[LARA]: pedido"), 42)
        self.assertIn("nenhum canal aceitou notificação hid=42", self.stdout.getvalue())

    async def test_lookup_failure_does_not_lose_persisted_handoff(self):
        self.lookup_error = True
        self.assertEqual(await db.create_handoff("+15550000003", "levvai", "[LARA]: pedido"), 42)
        self.discord.assert_called_once_with("levvai", "+15550000003", "[LARA]: pedido")
        self.clinical.assert_not_called()


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        self.client = Mock()
        self.client.messages.create.return_value = SimpleNamespace(sid="SM-test", status="queued")
        self.client_factory = patch.object(notif, "_client", return_value=self.client).start()
        self.urlopen = patch.object(notif.urllib.request, "urlopen").start()
        self.stdout = io.StringIO()
        self.redirect = redirect_stdout(self.stdout)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def clinical_alert(self, sender="+15550000001", manager="+15550000002"):
        return notif.notify_escalacao_gerente(sender, manager, "+15550000003", "[LARA]: precisa de avaliação")

    def test_queued_is_acceptance_not_delivery(self):
        self.assertTrue(self.clinical_alert("whatsapp:+15550000001", "15550000002"))
        sent = self.client.messages.create.call_args.kwargs
        self.assertEqual(sent["from_"], "whatsapp:+15550000001")
        self.assertEqual(sent["to"], "whatsapp:+15550000002")
        self.assertNotIn("[LARA]", sent["body"])
        self.assertIn("entrega não confirmada", self.stdout.getvalue())

    def test_missing_sender_never_falls_back_to_another_tenant(self):
        os.environ["TWILIO_FROM_NUMBER"] = "+15550000009"
        self.assertFalse(self.clinical_alert(sender=""))
        self.client.messages.create.assert_not_called()

    def test_invalid_manager_is_not_sent(self):
        self.assertFalse(self.clinical_alert(manager=""))
        self.client.messages.create.assert_not_called()

    def test_missing_twilio_is_reported(self):
        self.client_factory.return_value = None
        self.assertFalse(self.clinical_alert())
        self.assertIn("Twilio não configurado", self.stdout.getvalue())

    def test_twilio_exception_is_best_effort(self):
        self.client.messages.create.side_effect = RuntimeError("Twilio failure")
        self.assertFalse(self.clinical_alert())

    def test_rejected_status_is_not_success(self):
        self.client.messages.create.return_value.status = "undelivered"
        self.assertFalse(self.clinical_alert())

    def test_discord_requires_handoff_specific_env(self):
        os.environ["DISCORD_WEBHOOK_URL"] = "https://example.invalid/smoke"
        self.assertFalse(notif.notify_handoff_discord("Casa", "cliente", "motivo"))
        self.urlopen.assert_not_called()

    def test_discord_uses_configured_handoff_channel(self):
        os.environ["DISCORD_HANDOFF_WEBHOOK_URL"] = "https://example.invalid/handoff"
        self.assertTrue(notif.notify_handoff_discord("Casa", "cliente", "motivo"))
        request = self.urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.invalid/handoff")
        self.assertIn("Casa", json.loads(request.data)["content"])

    def test_discord_failure_returns_false(self):
        os.environ["DISCORD_HANDOFF_WEBHOOK_URL"] = "https://example.invalid/handoff"
        self.urlopen.side_effect = RuntimeError("Discord failure")
        self.assertFalse(notif.notify_handoff_discord("Casa", "cliente", "motivo"))

    def test_send_to_customer_still_propagates_twilio_failure(self):
        self.client.messages.create.side_effect = RuntimeError("Twilio failure")
        with self.assertRaisesRegex(RuntimeError, "Twilio failure"):
            notif.send_to_customer("+15550000001", "+15550000003", "Resposta")


if __name__ == "__main__":
    unittest.main()
