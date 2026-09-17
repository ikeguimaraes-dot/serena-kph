"""Offline usage/agent/webhook regression tests: no SDK calls or messages sent."""
import ast
import asyncio
import base64
import os
import time
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

from llm_usage import observed_call, metric_cost_fields

ROOT = Path(__file__).parent


def response(*, model="claude-sonnet-4-6", input=1000, output=100, creation=2000, read=3000, **kw):
    return NS(model=model, usage=NS(input_tokens=input, output_tokens=output,
              cache_creation_input_tokens=creation, cache_read_input_tokens=read, **kw))


def agent_class(namespace):
    tree = ast.parse((ROOT / "agent.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RestaurantAgent")
    globals_ = dict(os=os, asyncio=asyncio, time=time, base64=base64, MAX_HISTORY=20,
                    MAX_ITERATIONS=6, MODEL="claude-sonnet-4-6", TOOLS=[],
                    observed_call=observed_call, metric_cost_fields=metric_cost_fields,
                    _detect_intent=lambda _: "reserva_nova", _detect_pediu_humano=lambda _: False,
                    _detect_admitiu_nao_saber=lambda _: False, _calc_cost_usd=lambda a,b: 0.0045)
    globals_.update(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "agent.py", "exec"), globals_)
    return globals_["RestaurantAgent"]


class PricingTests(unittest.TestCase):
    def test_cache_components_and_no_double_count(self):
        call = observed_call(response())
        self.assertEqual(Decimal(call["cost_usd"]), Decimal("0.0129"))
        fields = metric_cost_fields([call, call])
        self.assertEqual(fields["custo_total_usd"], Decimal("0.0258"))
        self.assertEqual(fields["tokens_cache_creation"], 4000)
        self.assertEqual(fields["tokens_cache_read"], 6000)
        self.assertNotIn("custo_usd", fields, "Legacy field is not overwritten")

    def test_mixed_cache_ttl(self):
        call = observed_call(response(input=0, output=10, creation=300, read=0,
            cache_creation=NS(ephemeral_5m_input_tokens=100, ephemeral_1h_input_tokens=200)))
        self.assertEqual(Decimal(call["cost_usd"]), Decimal("0.001725"))

    def test_unknown_or_missing_usage_not_assumed_free(self):
        for item in (response(model="future-model"), NS(model="claude-sonnet-4-6", usage=None),
                     NS(model="claude-sonnet-4-6", usage=NS(input_tokens=100,output_tokens=10))):
            fields = metric_cost_fields([observed_call(item)])
            self.assertIsNone(fields["custo_total_usd"])
            self.assertNotEqual(fields["custo_status"], "complete")
        self.assertIsNone(observed_call(response(model="claude-sonnet-4-60"))["cost_usd"])
        self.assertEqual(observed_call(response(model="claude-sonnet-4-6-20260217"))["status"], "complete")


class ReportRouteTests(unittest.TestCase):
    def test_endpoint_is_private_and_read_only(self):
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.testclient import TestClient
        from commercial_report import create_router
        def privileged(x_admin_secret: str | None = Header(None)):
            if x_admin_secret != "synthetic-admin":
                raise HTTPException(403, "Denied")
        app = FastAPI()
        app.include_router(create_router(privileged))
        with TestClient(app) as client, patch("commercial_report.build_report", new_callable=AsyncMock) as report:
            report.return_value = {"restaurant_id":"unit-a","receita_realizada_brl":None}
            url="/api/restaurants/unit-a/reports/commercial?inicio=2026-09-01&fim=2026-09-08"
            self.assertEqual(client.get(url).status_code,403)
            report.assert_not_awaited()
            result=client.get(url,headers={"x-admin-secret":"synthetic-admin"})
            self.assertEqual(result.status_code,200)
            self.assertIsNone(result.json()["receita_realizada_brl"])
            self.assertEqual(report.await_args.args[0],"unit-a")
            self.assertEqual(client.post(url,headers={"x-admin-secret":"synthetic-admin"}).status_code,405)
            self.assertEqual(client.get(url.replace("2026-09-01","invalid"),headers={"x-admin-secret":"synthetic-admin"}).status_code,422)


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_explicit_tenant_and_separate_cache(self):
        from typing import Optional
        from fastapi import Query
        tree = ast.parse((ROOT / "main.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "serena_metrics")
        node.decorator_list = []
        db = NS(serena_overview=AsyncMock(side_effect=lambda days, restaurant_id: {"unit": restaurant_id}))
        namespace = dict(os=os, Optional=Optional, Query=Query, db=db,
                         _periodo_to_days=lambda _: 7, _serena_metrics_cache={})
        exec(compile(ast.Module(body=[node], type_ignores=[]), "main.py", "exec"), namespace)
        with patch.dict(os.environ, {"AGENT_NAME": "fallback"}, clear=True):
            self.assertEqual(await namespace["serena_metrics"]("7d", "unit-a"), {"unit": "unit-a"})
            self.assertEqual(await namespace["serena_metrics"]("7d", "unit-b"), {"unit": "unit-b"})
            self.assertEqual(await namespace["serena_metrics"]("7d", None), {"unit": "fallback"})
        self.assertEqual(db.serena_overview.await_count, 3)

    async def test_current_inbound_saved_before_tools_without_duplicate_context(self):
        calls = []
        async def save(*args, **kwargs):
            calls.append((args, kwargs)); return 1
        db = NS(get_restaurant_by_whatsapp=AsyncMock(return_value={"id":"unit-a","nome":"A"}),
                ensure_contact=AsyncMock(), is_in_handoff=AsyncMock(return_value=False),
                get_history=AsyncMock(return_value=[{"role":"user","content":"older"}]),
                save_message=save, record_serena_metric=AsyncMock(return_value="metric"))
        obj = agent_class({"db":db,"build_prompt":AsyncMock(return_value=("system",1))})()
        async def run(**kwargs):
            self.assertEqual(calls[0][1], {"source_message_sid":"SM-test","ctwa_clid":"click-a"})
            self.assertEqual([m["content"] for m in kwargs["messages"]], ["older","book"])
            return {"text":"ok","tokens_input":1000,"tokens_output":100,"tools_called":[],
                    "usage_calls":[observed_call(response())]}
        obj._run = run
        with patch.dict(os.environ, {}, clear=True):
            answer = await obj.process("+test", "+unit", "book", source_message_sid="SM-test",ctwa_clid="click-a")
        self.assertEqual(answer, "ok")
        self.assertEqual([c[0][2] for c in calls], ["user", "assistant"])
        db.get_history.assert_awaited_once_with("+test","unit-a",20,exclude_source_message_sid="SM-test")
        metric = db.record_serena_metric.await_args.args[0]
        self.assertEqual(metric["custo_total_usd"], Decimal("0.0129"))
        self.assertEqual(metric["custo_usd"], 0.0045)

    async def test_handoff_keeps_referral_without_llm(self):
        db = NS(get_restaurant_by_whatsapp=AsyncMock(return_value={"id":"unit-a","nome":"A"}),
                ensure_contact=AsyncMock(),is_in_handoff=AsyncMock(return_value=True),save_message=AsyncMock())
        obj = agent_class({"db":db})()
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(await obj.process("+test", "+unit", "hello",source_message_sid="SM-handoff",ctwa_clid="click-handoff"))
        self.assertEqual(db.save_message.await_args.kwargs["ctwa_clid"], "click-handoff")

    async def test_usage_accumulates_every_tool_iteration(self):
        first = response(); first.stop_reason="tool_use"
        first.content=[NS(type="tool_use",name="fake_tool",id="tool1",input={})]
        second = response(); second.stop_reason="end_turn"; second.content=[NS(type="text",text="done")]
        client = NS(messages=NS(create=Mock(side_effect=[first,second])))
        obj = agent_class({"client":client,"execute_tool":AsyncMock(return_value="result")})()
        result = await obj._run("system",[],"+test","unit-a")
        self.assertEqual(result["tokens_input"], 2000)
        self.assertEqual(len(result["usage_calls"]), 2)
        self.assertEqual(metric_cost_fields(result["usage_calls"])["custo_total_usd"], Decimal("0.0258"))

    async def test_webhook_passes_exact_provider_fields(self):
        tree = ast.parse((ROOT / "main.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "whatsapp_webhook")
        node.decorator_list=[]
        tasks=NS(add_task=Mock()); process=object()
        namespace={"BackgroundTasks":object,"Form":lambda v=None: v,"MAX_MSG_LEN":2000,
                   "_twiml_ack":lambda: "ack","_process_and_reply":process}
        exec(compile(ast.Module(body=[node],type_ignores=[]),"main.py","exec"),namespace)
        result=await namespace["whatsapp_webhook"](tasks,From="whatsapp:+test",To="whatsapp:+unit",Body="book",
                    MessageSid="SM-unique",ReferralCtwaClid="click-exact")
        self.assertEqual(result,"ack")
        self.assertEqual(tasks.add_task.call_args.args[-2:],("SM-unique","click-exact"))


if __name__ == "__main__":
    unittest.main()
