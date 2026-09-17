"""Isolated restored-DB integration hook. No external HTTP or customer messages."""
import asyncio
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg
from fastapi import HTTPException
import database as db
import outreach as o


async def run():
    host=os.environ.get("PGHOST","")
    if not host.startswith("/tmp/serena-restore-") or os.environ.get("PGDATABASE")!="serena_restore":
        raise RuntimeError("Only the backup runner's isolated Unix socket is allowed")
    pool=await asyncpg.create_pool(host=host,port=int(os.environ["PGPORT"]),user=os.environ["PGUSER"],database="serena_restore",ssl=False,min_size=1,max_size=5)
    db._pool=pool
    try:
        migrations=Path(__file__).with_name("migrations")
        async with pool.acquire() as c:
            for name in ("20260917043459_ctwa_cache_commercial_reporting.sql", "20260917044853_consented_outreach_outbox.sql",
                         "20260917045116_crm_loss_reason_history.sql", "20260917050855_reservation_outreach_schedule.sql"):
                await c.execute((migrations/name).read_text())
            await c.execute((migrations/"20260917050855_reservation_outreach_schedule.sql").read_text())
            assert await c.fetchval("SELECT count(*) FROM pg_class WHERE relname IN ('outreach_outbox','outreach_rules','outreach_consent_events') AND relrowsecurity")==3
            for table in ("outreach_outbox","outreach_rules","outreach_consent_events"):
                assert not await c.fetchval("SELECT has_table_privilege('anon',$1,'SELECT')",table)
                assert not await c.fetchval("SELECT has_table_privilege('authenticated',$1,'INSERT')",table)
        nonce=uuid.uuid4().hex
        a,b="outreach-a-"+nonce,"outreach-b-"+nonce
        phone="+551100000002"
        for rid,sender in ((a,"+551100000001"),(b,"+551100000003")):
            await pool.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,true)",rid,sender)
            await db.ensure_contact(phone,"Synthetic",rid)
            await pool.execute("UPDATE contacts SET lead_score='morno',opt_in_marketing=true,atualizado_em=NOW()-INTERVAL '4 days' WHERE restaurant_id=$1 AND celular=$2",rid,phone)
            await pool.execute("INSERT INTO conversations(restaurant_id,user_phone,role,content,created_at) VALUES($1,$2,'user','Synthetic',NOW()-INTERVAL '4 days')",rid,phone)
        assert not (await o.consent_history(a,phone))["eligible"]  # legacy bool is no evidence
        assert not (await o.rules_for(a))["rules"][0]["enabled"]
        consent=o.ConsentChange(granted=True,source="form",occurred_at=o.utcnow()-timedelta(days=2),evidence="Synthetic consent form record")
        await o.record_consent(a,phone,consent,"synthetic-operator")
        assert (await o.consent_history(a,phone))["eligible"]
        assert not (await o.consent_history(b,phone))["eligible"]
        # A booking in B cannot suppress A's otherwise eligible nurture event.
        await db.criar_reserva({"restaurant_id":b,"cliente_phone":phone,"cliente_nome":"Synthetic","data":o.utcnow().date()+timedelta(days=1),"hora_inicio":"19:00","posicoes":1}, allow_legacy=True)
        approval=AsyncMock(return_value={"status":"approved","verified_at":o.utcnow()})
        with patch.object(o,"verify_template",approval):
            for stage in ("nurture_d3","d1"):
                await o.save_rule(a,stage,o.RuleChange(enabled=True,content_sid="HX"+"a"*32),"synthetic-operator")
        preview=await o.preview(a,"nurture")
        assert len(preview["items"])==1 and preview["items"][0]["eligible"]
        assert await pool.fetchval("SELECT count(*) FROM outreach_outbox WHERE restaurant_id=$1",a)==0
        assert await db.get_nurture_leads(restaurant_id=a)
        assert not await db.get_nurture_leads(restaurant_id=b)
        calls=[]
        async def accepted(attempt):
            calls.append(attempt)
            await asyncio.sleep(0.02)  # let competing worker reach claim
            return {"status":"sent","provider_message_sid":"SM"+"b"*32,"provider_status":"queued"}
        with patch.dict(os.environ,{"SERENA_OUTREACH_SEND_ENABLED":"true"}), patch.object(o,"provider_credentials",return_value=("AC"+"c"*32,"synthetic")), patch.object(o,"verify_template",approval), patch.object(o,"send_template",accepted):
            results=await asyncio.gather(o.run(a,"nurture",False),o.run(a,"nurture",False))
            assert len(calls)==1 and sum(result["sent"] for result in results)==1
            await o.run(a,"nurture",False)
            assert len(calls)==1
        assert calls[0]["sender_phone"]=="+551100000001"
        assert await pool.fetchval("SELECT count(*) FROM outreach_outbox WHERE restaurant_id=$1",a)==1
        assert await pool.fetchval("SELECT notas FROM contacts WHERE restaurant_id=$1 AND celular=$2",a,phone) is None

        async def event(customer):
            await db.ensure_contact(customer,"Synthetic",a)
            await o.record_consent(a,customer,consent,"synthetic-operator")
            order=await db.criar_os({"restaurant_id":a,"cliente_phone":customer,"cliente_nome":"Synthetic","tipo_evento":"Synthetic","data":o.utcnow().date()-timedelta(days=1),"pessoas":1,"status":"realizado"})
            await pool.execute("UPDATE ordens_servico SET evento_realizado_em=NOW()-INTERVAL '24 hours' WHERE id=$1",order["id"])
            return order
        successful=await event("+551100000004")
        unknown=await event("+551100000005")
        rejected=await event("+551100000006")
        async def outcomes(attempt):
            calls.append(attempt)
            if attempt["customer_phone"].endswith("004"):
                return {"status":"sent","provider_message_sid":"SM"+"d"*32,"provider_status":"queued"}
            if attempt["customer_phone"].endswith("005"):
                return {"status":"unknown","error_code":"synthetic_timeout"}
            return {"status":"failed","error_code":"synthetic_rejection"}
        with patch.dict(os.environ,{"SERENA_OUTREACH_SEND_ENABLED":"true"}), patch.object(o,"provider_credentials",return_value=("AC"+"c"*32,"synthetic")), patch.object(o,"verify_template",approval), patch.object(o,"send_template",outcomes):
            await o.run(a,"pos_evento",False)
            after=len(calls)
            await o.run(a,"pos_evento",False)
            assert len(calls)==after
        for order,expected in ((successful,True),(unknown,False),(rejected,False)):
            marked=await pool.fetchval("SELECT regua_d1_enviado_em IS NOT NULL FROM ordens_servico WHERE id=$1",order["id"])
            assert marked is expected
        # Database invariant prevents false sent even if a future caller is buggy.
        async with pool.acquire() as c:
            try:
                async with c.transaction():
                    await c.execute("UPDATE outreach_outbox SET status='sent',provider_message_sid=NULL WHERE restaurant_id=$1 AND status='unknown'",a)
                raise AssertionError("sent without SID must fail")
            except asyncpg.CheckViolationError:
                pass
        try:
            await db.marcar_regua_enviada(str(unknown["id"]),"d1")
            raise AssertionError("legacy helper must require provider evidence")
        except ValueError:
            pass
        # Revocation wins before claim, and old imported grants cannot undo it.
        revoke=o.ConsentChange(granted=False,source="revocation",occurred_at=o.utcnow()-timedelta(seconds=1),evidence="Synthetic explicit revocation")
        await o.record_consent(a,phone,revoke,"synthetic-operator")
        assert not (await o.consent_history(a,phone))["eligible"]
        try:
            await o.record_consent(a,phone,consent,"synthetic-operator")
            raise AssertionError("stale consent cannot undo revocation")
        except HTTPException as error:
            assert error.status_code==409
        assert not await db.get_nurture_leads(restaurant_id=a)
        print(json.dumps({"success":True,"migration_replay":True,"rls_and_browser_privileges":True,
            "legacy_boolean_not_consent":True,"consent_evidence_actor_and_revocation":True,
            "tenant_sender_and_reservation_isolation":True,"dry_run_no_outbox_writes":True,
            "concurrent_event_single_attempt":True,"sent_requires_sid":True,
            "unknown_and_failed_not_retried_or_marked_sent":True,"external_messages_sent":0}))
    finally:
        db._pool=None
        await pool.close()


if __name__=="__main__": asyncio.run(run())
