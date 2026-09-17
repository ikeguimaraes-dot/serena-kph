"""Restore-hook integration checks. Refuses all non-disposable database targets.

Run ONLY through scripts/serena_backup.py --backup ... --restore-hook THIS_FILE.
The runner restores a private local copy, executes this hook and destroys it.
No external messages, APIs, production writes or environment-file loading.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS

import asyncpg
import database as db
from commercial_report import build_report, TIMEZONE
from llm_usage import observed_call, metric_cost_fields
from test_recovery_contract import TransactionPool

HERE = Path(__file__).parent


async def run():
    host = os.environ.get("PGHOST", "")
    if not host.startswith("/tmp/serena-restore-") or os.environ.get("PGDATABASE") != "serena_restore":
        raise RuntimeError("Refusing target: only backup runner's isolated Unix socket is allowed")
    c = await asyncpg.connect(host=host, port=int(os.environ["PGPORT"]),
                             user=os.environ["PGUSER"], database="serena_restore", ssl=False)
    db._pool = TransactionPool(c)
    try:
        legacy_before = await c.fetchrow("SELECT count(*) AS n,sum(custo_usd) AS legacy FROM serena_metrics")
        migration = (HERE / "migrations/20260917043459_ctwa_cache_commercial_reporting.sql").read_text()
        await c.execute(migration)
        await c.execute(migration)  # additive/idempotent replay
        await c.execute((HERE / "migrations/20260917045116_crm_loss_reason_history.sql").read_text())
        assert dict(legacy_before) == dict(await c.fetchrow("SELECT count(*) AS n,sum(custo_usd) AS legacy FROM serena_metrics"))
        nonce = uuid.uuid4().hex
        a, b = "instrument-a-" + nonce, "instrument-b-" + nonce
        phone = "+12025550110"
        for index, rid in enumerate((a, b)):
            await c.execute("INSERT INTO restaurants(id,nome,whatsapp_number,ativo) VALUES($1,$1,$2,true)",rid,f"+1202555019{index}")
            await db.ensure_contact(phone,rid,rid)
        base = datetime.now(timezone.utc) - timedelta(days=1)
        sid = "SM" + nonce
        first = await db.save_message(phone,a,"user","book",source_message_sid=sid,ctwa_clid="click-a")
        assert first is not None
        assert await db.save_message(phone,a,"user","book",source_message_sid=sid,ctwa_clid="click-a") is None
        await db.save_message(phone,a,"user","book",source_message_sid="SMdifferent"+nonce)
        await db.save_message(phone,a,"user","book")
        await db.save_message(phone,a,"user","book")
        assert await c.fetchval("SELECT count(*) FROM conversations WHERE restaurant_id=$1",a)==4
        # Same SID in another unit is not suppressed and must never cross attribution.
        await db.save_message(phone,b,"user","other",source_message_sid=sid,ctwa_clid="click-b")
        await c.execute("UPDATE conversations SET created_at=$2 WHERE restaurant_id=$1",a,base)
        await c.execute("UPDATE conversations SET created_at=$2 WHERE restaurant_id=$1",b,base+timedelta(minutes=1))
        history = await db.get_history(phone,a,20,exclude_source_message_sid=sid)
        assert len(history)==3
        usage = observed_call(NS(model="claude-sonnet-4-6",usage=NS(input_tokens=1000,output_tokens=100,
                                  cache_creation_input_tokens=2000,cache_read_input_tokens=3000)))
        cost = metric_cost_fields([usage])
        metric_id = await db.record_serena_metric({"restaurant_id":a,"user_phone":phone,
                      "tokens_input":1000,"tokens_output":100,"custo_usd":Decimal("0.0045"),
                      "intencao_detectada":"reserva_nova", "source_message_sid":sid, **cost})
        await c.execute("UPDATE serena_metrics SET horario_conversa=$2 WHERE id::text=$1",metric_id,base+timedelta(minutes=2))
        await db.record_serena_metric({"restaurant_id":a,"user_phone":phone,"custo_usd":Decimal("0.01")})
        await db.record_serena_metric({"restaurant_id":b,"user_phone":phone,"custo_usd":Decimal("99")})

        async def reserve(rid, customer=phone):
            return await db.criar_reserva({"restaurant_id":rid,"cliente_phone":customer,"cliente_nome":"Synthetic",
                "data":datetime.now(TIMEZONE).date()+timedelta(days=3),"hora_inicio":"19:00","posicoes":1}, allow_legacy=True)
        reserved = await reserve(a)
        assert reserved["ctwa_clid"] == "click-a" and reserved["ctwa_source_message_sid"] == sid
        assert (await reserve(b))["ctwa_clid"] == "click-b"
        await db.atualizar_status_reserva(str(reserved["id"]),a,"realizada")
        missed = await reserve(a)
        await db.atualizar_status_reserva(str(missed["id"]),a,"no_show")
        # A later referral does not mutate existing snapshots.
        newer = await db.save_message(phone,a,"user","later",source_message_sid="SMnew"+nonce,ctwa_clid="click-new")
        assert (await db.get_reserva(str(reserved["id"])))["ctwa_clid"] == "click-a"
        assert (await reserve(a))["ctwa_clid"] == "click-new"
        for suffix,offset,customer in (("old",-8,"+12025550111"),("future",1,"+12025550112")):
            row_id=await db.save_message(customer,a,"user","source",source_message_sid="SM"+suffix+nonce,ctwa_clid="click-"+suffix)
            await c.execute("UPDATE conversations SET created_at=$2 WHERE id=$1",row_id,datetime.now(timezone.utc)+timedelta(days=offset))
            assert (await reserve(a,customer))["ctwa_clid"] is None
        no_prior=await reserve(a,"+12025550113")
        await db.save_message("+12025550113",a,"user","late",ctwa_clid="late-click")
        assert (await db.get_reserva(str(no_prior["id"])))["ctwa_clid"] is None

        # In the real agent the metric is recorded AFTER reservation tools. The
        # funnel must link to the inbound timestamp by SID, not lose this booking.
        await c.execute("UPDATE serena_metrics SET horario_conversa=NOW() WHERE id::text=$1",metric_id)
        await c.execute("""INSERT INTO ordens_servico
            (restaurant_id,cliente_phone,cliente_nome,tipo_evento,data,hora_inicio,pessoas,
             status,plano,proposta_validade,criado_em)
            VALUES($1,$2,'Synthetic proposal','Synthetic',CURRENT_DATE+3,'19:00',2,
                   'proposta_enviada','Synthetic plan',$3,$4)""",
            a, phone, base + timedelta(days=4), base + timedelta(minutes=3))

        today=datetime.now(TIMEZONE).date()
        report=await build_report(a,today-timedelta(days=7),today+timedelta(days=1))
        funnel=report["funil_por_contato"]
        assert funnel["contatos_com_intencao_reserva_ou_evento"] == 1
        assert funnel["contatos_com_proposta_registrada"] == 1
        assert funnel["contatos_com_reserva_registrada"] == 1
        assert funnel["contatos_com_confirmacao_ou_desfecho"] == 1
        assert funnel["contatos_com_reserva_realizada"] == 1 and funnel["contatos_com_no_show"] == 1
        assert report["custo_llm"]["total_observado_usd"] == 0.0129
        assert report["custo_llm"]["turnos_sem_custo_completo"] == 1
        assert report["receita_realizada_brl"] is None and report["custo_twilio_usd"] is None and report["roi"] is None
        other=await build_report(b,today-timedelta(days=7),today+timedelta(days=1))
        assert other["funil_por_contato"]["contatos_com_intencao_reserva_ou_evento"] == 0
        assert other["funil_por_contato"]["contatos_com_proposta_registrada"] == 0
        assert other["funil_por_contato"]["contatos_com_reserva_registrada"] == 0
        assert other["funil_por_contato"]["contatos_com_confirmacao_ou_desfecho"] == 0
        assert other["custo_llm"]["total_observado_usd"] is None

        # Weekly SQL compiles against restored production schema and tenant CRM.
        import serena_weekly
        await c.execute("UPDATE contacts SET ltv_total=10 WHERE restaurant_id=$1 AND celular=$2",a,phone)
        await c.execute("UPDATE contacts SET ltv_total=9999 WHERE restaurant_id=$1 AND celular=$2",b,phone)
        ltv=await serena_weekly._get_ltv_top5(a)
        assert len(ltv)==1 and ltv[0]["ltv_total"]==10
        weekly=await serena_weekly._get_receita_semana(a,7)
        assert weekly["leads"] > 0 and weekly["convertidos"] <= weekly["leads"]
        print(json.dumps({"success":True,"migration_replay":True,"legacy_cost_preserved":True,
            "sid_persistence_idempotency":True,"same_text_distinct_or_missing_sid_preserved":True,
            "ctwa_same_tenant_last_touch_7d":True,"future_expired_and_retroactive_attribution_rejected":True,
            "funnel_and_cost_tenant_isolation":True,"existing_outcome_statuses_work":True,
            "same_turn_reservation_before_metric_is_counted":True,
            "proposal_funnel_uses_real_os_and_tenant_scope":True,
            "weekly_sql_and_ltv_tenant_scope":True,"external_messages_sent":0}))
    finally:
        db._pool=None
        await c.close()


if __name__ == "__main__":
    asyncio.run(run())
