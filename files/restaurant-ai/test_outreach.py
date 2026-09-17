"""Offline outreach checks; all HTTP transports are mocked."""
import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
import outreach as o


class ContractTests(unittest.TestCase):
    def test_explicit_consent_validation(self):
        base = {"granted": True, "source": "whatsapp_explicit", "occurred_at": o.utcnow()-timedelta(minutes=1), "evidence": "Mensagem explícita de autorização"}
        self.assertTrue(o.ConsentChange(**base).granted)
        for change in ({"occurred_at": o.utcnow().replace(tzinfo=None)}, {"occurred_at": o.utcnow()+timedelta(days=1)},
                       {"evidence": "        "}, {"source": "revocation"}, {"source": "conversation"}, {"actor_id": "forged"}):
            with self.assertRaises(ValidationError):
                o.ConsentChange(**{**base, **change})

    def test_private_api_and_server_actor(self):
        async def privileged(request: Request, x_admin_secret: str | None = Header(None)):
            if x_admin_secret != "test-only": raise HTTPException(403, "Denied")
            request.state.operator = {"id": "server-actor"}
        app=FastAPI(); app.include_router(o.create_router(privileged))
        with TestClient(app) as client, patch.object(o, "record_consent", new_callable=AsyncMock) as record:
            record.return_value={"granted":True}
            url="/api/restaurants/unit-a/contacts/%2B551100000001/outreach-consent"
            body={"granted":True,"source":"form","occurred_at":(o.utcnow()-timedelta(minutes=1)).isoformat(),"evidence":"Formulário comprovado"}
            self.assertEqual(client.put(url,json=body).status_code,403); record.assert_not_awaited()
            self.assertEqual(client.put(url,json=body,headers={"x-admin-secret":"test-only"}).status_code,200)
            self.assertEqual(record.await_args.args[0],"unit-a")
            self.assertEqual(record.await_args.args[-1],"server-actor")


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def transport(self, handler):
        original=httpx.AsyncClient
        return patch.object(o.httpx,"AsyncClient",side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler),**kwargs))

    async def test_provider_acceptance_requires_sid_and_unknown_never_claims_sent(self):
        attempt={"sender_phone":"+551100000001","customer_phone":"+551100000002","content_sid":"HX"+"a"*32,
                 "payload":{"variables":{"1":"Teste"}}}
        for code,body,status in ((201,{"sid":"SM"+"b"*32,"status":"queued"},"sent"),
                                 (201,{"status":"queued"},"unknown"), (500,{},"unknown"),(400,{},"failed"),
                                 (201,{"sid":"SM"+"b"*32,"status":"failed"},"failed")):
            calls=[]
            def handler(request):
                calls.append(request)
                return httpx.Response(code,json=body)
            with patch.object(o,"provider_credentials",return_value=("AC"+"c"*32,"synthetic")), self.transport(handler):
                result=await o.send_template(attempt)
            self.assertEqual(result["status"],status); self.assertEqual(len(calls),1)
            self.assertNotIn("Body=",calls[0].content.decode())
        def timeout(request): raise httpx.ReadTimeout("synthetic",request=request)
        with patch.object(o,"provider_credentials",return_value=("AC"+"c"*32,"synthetic")), self.transport(timeout):
            self.assertEqual((await o.send_template(attempt))["status"],"unknown")

    async def test_unavailable_provider_does_not_send(self):
        with patch.object(o,"provider_credentials",return_value=None), patch.object(o.httpx,"AsyncClient") as client:
            self.assertEqual((await o.send_template({}))["status"],"failed")
            client.assert_not_called()

    async def test_only_current_approved_template_is_accepted(self):
        for status in ("approved","paused","rejected","pending"):
            with patch.object(o,"provider_credentials",return_value=("AC"+"c"*32,"synthetic")), self.transport(lambda _:httpx.Response(200,json={"whatsapp":{"status":status}})):
                if status=="approved": self.assertEqual((await o.verify_template("HX"+"a"*32))["status"],"approved")
                else:
                    with self.assertRaises(HTTPException): await o.verify_template("HX"+"a"*32)

    async def test_default_and_disabled_runs_only_preview(self):
        for dry,enabled in ((True,True),(True,False),(False,False)):
            with patch.object(o,"preview",new_callable=AsyncMock,return_value={"items":[],"sent":0,"dry_run":True}), \
                 patch.object(o,"sending_enabled",return_value=enabled), patch.object(o,"claim",new_callable=AsyncMock) as claim, \
                 patch.object(o,"send_template",new_callable=AsyncMock) as send:
                result=await o.run("unit-a","nurture",dry)
                self.assertTrue(result["dry_run"]); claim.assert_not_awaited(); send.assert_not_awaited()


if __name__=="__main__": unittest.main()
