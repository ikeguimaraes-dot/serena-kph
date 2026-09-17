"""Synthetic multimodal contract; mocked model only, no network or persistence."""
import base64
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "synthetic-test-key-not-used")
import agent

source = Path(__file__).resolve().parents[2] / "scripts" / "validate_vision_readonly.py"
spec = importlib.util.spec_from_file_location("vision_readonly_audit", source)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class VisionContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_actual_run_keeps_base64_image_and_never_calls_process_or_database(self):
        image = audit.synthetic_png()
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        response = NS(stop_reason="end_turn", content=[NS(type="text", text="Um círculo vermelho, quadrado azul e triângulo verde; a imagem não informa preço ou estoque.")], usage=None)
        with patch.object(agent.client.messages, "create", return_value=response) as create, \
             patch.object(agent.RestaurantAgent, "process", new_callable=AsyncMock) as process, \
             patch.object(agent.db, "pool", side_effect=AssertionError("No DB access")), \
             patch.object(agent, "execute_tool", new_callable=AsyncMock) as dispatch:
            result = await agent.RestaurantAgent()._run("Synthetic system", audit.image_message(image), "+synthetic", "meet_and_eat", read_only=True)
        image_block = create.call_args.kwargs["messages"][0]["content"][0]
        self.assertEqual(image_block["source"]["media_type"], "image/png")
        self.assertEqual(base64.b64decode(image_block["source"]["data"]), image)
        self.assertTrue(all(audit.factual_checks(result["text"]).values()))
        process.assert_not_awaited()
        dispatch.assert_not_awaited()

    async def test_multimodal_write_tool_is_blocked_and_image_survives_followup(self):
        image = audit.synthetic_png()
        tool = NS(stop_reason="tool_use", content=[NS(type="tool_use", id="synthetic-tool", name="fazer_reserva", input={})], usage=None)
        done = NS(stop_reason="end_turn", content=[NS(type="text", text="Não confirmei reserva.")], usage=None)
        with patch.object(agent.client.messages, "create", side_effect=[tool, done]) as create, \
             patch.object(agent.db, "pool", side_effect=AssertionError("No DB access")), \
             patch.object(agent, "execute_tool", new_callable=AsyncMock) as dispatch:
            result = await agent.RestaurantAgent()._run("Synthetic system", audit.image_message(image), "+synthetic", "freneze", read_only=True)
        dispatch.assert_not_awaited()
        self.assertEqual(result["tools_called"], ["fazer_reserva"])
        messages = create.call_args.kwargs["messages"]
        self.assertEqual(base64.b64decode(messages[0]["content"][0]["source"]["data"]), image)
        self.assertIn("MODO_TESTE_SEM_ESCRITA", messages[-1]["content"][0]["content"])


if __name__ == "__main__":
    unittest.main()
