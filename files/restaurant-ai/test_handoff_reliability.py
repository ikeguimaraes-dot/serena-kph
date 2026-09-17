"""No-IO handoff reply, takeover and self-loop regression contracts."""
import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from test_instrumentation import agent_class, observed_call, response

ROOT=Path(__file__).parent


def function(name, values):
    tree=ast.parse((ROOT/'main.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name==name)
    node.decorator_list=[]
    namespace={"asyncio":asyncio,"HTTPException":HTTPException,"HandoffReply":object,
               "BackgroundTasks":object,"Form":lambda default=None:default,
               "_reports_cache":{},"_serena_metrics_cache":{},**values}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'main.py','exec'),namespace)
    return namespace[name]


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_or_missing_sid_does_not_save_human_reply_or_advance_status(self):
        database=NS(get_handoff_by_id=AsyncMock(return_value={"restaurant_id":"unit-a","user_phone":"+15550000003"}),
                    get_restaurant_full=AsyncMock(return_value={"whatsapp_number":"+15550000001"}),
                    record_human_handoff_reply=AsyncMock())
        notification=NS(send_to_customer=Mock(side_effect=RuntimeError("synthetic unavailable")))
        call=function("handoff_reply",{"db":database,"notif":notification})
        for result in ("exception",None):
            if result is None:
                notification.send_to_customer.side_effect=None; notification.send_to_customer.return_value=None
            with self.assertRaises(HTTPException) as error:
                await call(12,NS(atendente_nome="Operator",mensagem="Reply"))
            self.assertEqual(error.exception.status_code,502)
        database.record_human_handoff_reply.assert_not_awaited()

    async def test_accepted_sid_persists_and_does_not_claim_delivery(self):
        database=NS(get_handoff_by_id=AsyncMock(return_value={"restaurant_id":"unit-a","user_phone":"+15550000003"}),
                    get_restaurant_full=AsyncMock(return_value={"whatsapp_number":"+15550000001"}),
                    record_human_handoff_reply=AsyncMock())
        sid="SM"+"a"*32
        notification=NS(send_to_customer=Mock(return_value={"provider_message_sid":sid,"provider_status":"queued"}))
        call=function("handoff_reply",{"db":database,"notif":notification})
        result=await call(12,NS(atendente_nome="Operator",mensagem="Reply"))
        self.assertTrue(result["accepted"]); self.assertFalse(result["delivery_confirmed"])
        database.record_human_handoff_reply.assert_awaited_once_with(12,"Operator","Reply",sid)
        notification.send_to_customer.assert_called_with("+15550000001","+15550000003","Reply")
        database.record_human_handoff_reply.side_effect=RuntimeError("DB unavailable")
        with self.assertRaises(HTTPException) as error: await call(12,NS(atendente_nome="Operator",mensagem="Reply"))
        self.assertEqual(error.exception.status_code,503)
        self.assertEqual(error.exception.detail["provider_message_sid"],sid)

    async def test_takeover_during_model_turn_stops_bot_but_keeps_cost(self):
        database=NS(get_restaurant_by_whatsapp=AsyncMock(return_value={"id":"unit-a","nome":"A"}),
                    ensure_contact=AsyncMock(),is_in_handoff=AsyncMock(side_effect=[False,True]),
                    get_history=AsyncMock(return_value=[]),save_message=AsyncMock(),record_serena_metric=AsyncMock(return_value="metric"))
        agent=agent_class({"db":database,"build_prompt":AsyncMock(return_value=("system",1))})()
        agent._run=AsyncMock(return_value={"text":"model reply","tokens_input":1000,"tokens_output":100,
                          "tools_called":[],"usage_calls":[observed_call(response())]})
        with patch.dict("os.environ",{},clear=True):
            self.assertIsNone(await agent.process("+15550000003","+15550000001","book"))
        self.assertEqual(database.save_message.await_count,1)
        self.assertEqual(database.save_message.await_args.args[2],"user")
        database.record_serena_metric.assert_awaited_once()

    async def test_provider_signed_self_echo_is_acknowledged_without_processing(self):
        tasks=NS(add_task=Mock())
        call=function("whatsapp_webhook",{"_twiml_ack":lambda:"ack","MAX_MSG_LEN":2000,
                     "_process_and_reply":Mock(),"notif":NS(send_to_customer=Mock())})
        result=await call(tasks,From="whatsapp:+1 (555) 000-0001",To="whatsapp:+15550000001",Body="echo",NumMedia=0)
        self.assertEqual(result,"ack"); tasks.add_task.assert_not_called()


if __name__=='__main__': unittest.main()
