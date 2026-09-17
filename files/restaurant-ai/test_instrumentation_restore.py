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


async def verify_cost_coverage(c):
    """Exercise real SQL: coverage, retry costs and recorded prompt/tenant scope."""
    nonce = uuid.uuid4().hex
    a, b = "coverage-a-" + nonce, "coverage-b-" + nonce
    for index, rid in enumerate((a, b)):
        await c.execute("INSERT INTO restaurants(id,nome,nome_agente,whatsapp_number,ativo) VALUES($1,$1,'Current persona',$2,true)",
                        rid, f"+1202555009{index}")
    prompts = []
    for rid, version in ((a, "recorded-v1"), (a, "recorded-v2"), (b, "other-unit-version")):
        prompts.append(await db.insert_prompt_version(version, "Synthetic prompt", rid))
    base = datetime.now(timezone.utc) - timedelta(days=1)
    today = datetime.now(TIMEZONE).date()
    start, end = today - timedelta(days=2), today + timedelta(days=1)
    call = observed_call(NS(model="claude-sonnet-4-6", usage=NS(input_tokens=1000, output_tokens=100,
                         cache_creation_input_tokens=2000, cache_read_input_tokens=3000)))

    async def inbound(rid, phone, sid):
        key = await db.save_message(phone, rid, "user", "Synthetic inquiry", source_message_sid=sid)
        await c.execute("UPDATE conversations SET created_at=$2 WHERE id=$1", key, base)
        return key

    async def metric(rid, phone, sid, prompt_id, *, calls=1, intent="reserva_nova", complete=True):
        fields = metric_cost_fields([call] * calls) if complete else {}
        key = await db.record_serena_metric({"restaurant_id": rid, "user_phone": phone,
            "source_message_sid": sid, "prompt_versao_id": prompt_id, "intencao_detectada": intent,
            "custo_usd": Decimal("0.0045"), **fields})
        await c.execute("UPDATE serena_metrics SET horario_conversa=$2 WHERE id::text=$1", key, base + timedelta(minutes=1))
        return key

    first, second = "+12025550011", "+12025550012"
    sid1, sid2 = "SMcoverage1" + nonce, "SMcoverage2" + nonce
    await inbound(a, first, sid1)
    await inbound(a, second, sid2)
    await metric(a, first, sid1, prompts[0])
    await metric(a, second, sid2, prompts[1], calls=2, intent="cardapio")
    report = await build_report(a, start, end)
    cost = report["custo_llm"]
    assert cost["cobertura"]["status"] == "complete"
    assert cost["custo_por_contato_usd"] == 0.01935
    assert cost["total_observado_usd"] == 0.0387
    versions = {row["prompt_versao_id"]: row for row in cost["por_prompt_versao"]}
    assert versions[prompts[0]]["versao"] == "recorded-v1" and versions[prompts[0]]["contatos_com_intencao"] == 1
    assert versions[prompts[1]]["versao"] == "recorded-v2" and versions[prompts[1]]["turnos_com_intencao"] == 0

    # A retry may incur another observed call: preserve all its cost, not another contact.
    await metric(a, first, sid1, prompts[1])
    cost = (await build_report(a, start, end))["custo_llm"]
    assert cost["custo_por_contato_usd"] == 0.0258 and cost["cobertura"]["metricas"] == 3
    assert cost["cobertura"]["contatos_inbound"] == 2
    versions = {row["prompt_versao_id"]: row for row in cost["por_prompt_versao"]}
    assert versions[prompts[1]]["contatos_com_metricas"] == 2 and versions[prompts[1]]["turnos"] == 2
    await c.execute("UPDATE restaurants SET nome_agente='Renamed current persona' WHERE id=$1", a)
    assert (await build_report(a, start, end))["custo_llm"]["por_prompt_versao"] == cost["por_prompt_versao"]

    # Malformed legacy prompt IDs retain their metric ID but never disclose the other unit's label.
    await metric(a, first, sid1, prompts[2])
    await metric(a, first, sid1, None)
    versions = {row["prompt_versao_id"]: row for row in (await build_report(a, start, end))["custo_llm"]["por_prompt_versao"]}
    assert versions[prompts[2]]["versao"] is None and not versions[prompts[2]]["versao_resolvida"]
    assert versions[None]["versao"] is None and not versions[None]["versao_resolvida"]

    # Missing SID or metric (including a handoff without LLM) must not become zero cost.
    missing = await inbound(a, first, None)
    cost = (await build_report(a, start, end))["custo_llm"]
    assert cost["custo_por_contato_usd"] is None and cost["cobertura"]["mensagens_sem_sid"] == 1
    assert cost["cobertura"]["mensagens_sem_metricas"] == 1
    await c.execute("DELETE FROM conversations WHERE id=$1", missing)
    legacy = await metric(a, first, sid1, prompts[0], complete=False)
    cost = (await build_report(a, start, end))["custo_llm"]
    assert cost["custo_por_contato_usd"] is None and cost["cobertura"]["metricas_sem_custo_completo"] == 1
    await c.execute("DELETE FROM serena_metrics WHERE id::text=$1", legacy)

    # Equal SID in another unit or another phone cannot close a coverage gap.
    shared_sid = "SMsharedcoverage" + nonce
    gap = await inbound(a, first, shared_sid)
    await inbound(b, first, shared_sid)
    await metric(b, first, shared_sid, prompts[2])
    wrong_phone = await metric(a, second, shared_sid, prompts[0])
    cost = (await build_report(a, start, end))["custo_llm"]
    assert cost["custo_por_contato_usd"] is None
    assert cost["cobertura"]["mensagens_sem_metricas"] == 1
    assert cost["cobertura"]["metricas_sem_vinculo_inbound_periodo"] == 1
    other_cost = (await build_report(b, start, end))["custo_llm"]
    assert other_cost["custo_por_contato_usd"] == 0.0129
    assert other_cost["por_prompt_versao"][0]["versao"] == "other-unit-version"
    await c.execute("UPDATE serena_metrics SET custo_total_usd=0 WHERE restaurant_id=$1", b)
    zero_cost = (await build_report(b, start, end))["custo_llm"]
    assert zero_cost["custo_por_contato_usd"] == 0 and zero_cost["cobertura"]["status"] == "complete"
    await c.execute("DELETE FROM conversations WHERE id=$1", gap)
    await c.execute("DELETE FROM serena_metrics WHERE id::text=$1", wrong_phone)

    # Period boundaries require the inbound and metric in the same observed window.
    await c.execute("UPDATE conversations SET created_at=$3 WHERE restaurant_id=$1 AND source_message_sid=$2",
                    a, sid2, base - timedelta(days=30))
    cost = (await build_report(a, start, end))["custo_llm"]
    assert cost["custo_por_contato_usd"] is None and cost["cobertura"]["metricas_sem_vinculo_inbound_periodo"] == 1
    empty = (await build_report(a, today - timedelta(days=90), today - timedelta(days=89)))["custo_llm"]
    assert empty["custo_por_contato_usd"] is None and empty["cobertura"]["status"] == "no_data"
    assert empty["total_observado_usd"] is None and empty["por_prompt_versao"] == []


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
        assert report["custo_llm"]["custo_por_contato_usd"] is None
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
        await verify_cost_coverage(c)
        print(json.dumps({"success":True,"migration_replay":True,"legacy_cost_preserved":True,
            "sid_persistence_idempotency":True,"same_text_distinct_or_missing_sid_preserved":True,
            "ctwa_same_tenant_last_touch_7d":True,"future_expired_and_retroactive_attribution_rejected":True,
            "funnel_and_cost_tenant_isolation":True,"existing_outcome_statuses_work":True,
            "same_turn_reservation_before_metric_is_counted":True,
            "proposal_funnel_uses_real_os_and_tenant_scope":True,
            "per_contact_cost_requires_full_observed_coverage":True,
            "missing_legacy_or_unlinked_cost_keeps_mean_null":True,
            "duplicate_sid_metrics_preserve_observed_retry_cost":True,
            "prompt_versions_use_recorded_id_and_tenant_join":True,
            "prompt_metrics_never_use_current_persona_as_history":True,
            "weekly_sql_and_ltv_tenant_scope":True,"external_messages_sent":0}))
    finally:
        db._pool=None
        await c.close()


if __name__ == "__main__":
    asyncio.run(run())
