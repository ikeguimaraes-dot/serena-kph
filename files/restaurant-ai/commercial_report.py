"""Deterministic, tenant-scoped commercial report. No LLM, sends, or writes."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

VERSION = "commercial-cohort-v3"
TIMEZONE = ZoneInfo("America/Sao_Paulo")

FUNNEL_SQL = """
WITH conversations_in_period AS (
  SELECT user_phone, min(created_at) AS first_message, count(*) AS messages,
         bool_or(NULLIF(ctwa_clid,'') IS NOT NULL) AS has_ctwa
  FROM conversations
  WHERE restaurant_id=$1 AND role='user' AND created_at >= $2 AND created_at < $3
  GROUP BY user_phone
), intents AS (
  SELECT c.user_phone, min(coalesce(source.created_at,m.horario_conversa)) AS first_intent
  FROM conversations_in_period c
  JOIN serena_metrics m ON m.user_phone=c.user_phone AND m.restaurant_id=$1
    AND m.intencao_detectada IN ('reserva_nova','evento')
  LEFT JOIN conversations source ON source.restaurant_id=m.restaurant_id
    AND source.user_phone=m.user_phone AND source.role='user'
    AND source.source_message_sid=m.source_message_sid
  WHERE coalesce(source.created_at,m.horario_conversa) >= c.first_message
    AND coalesce(source.created_at,m.horario_conversa) < $3
  GROUP BY c.user_phone
), proposals AS (
  SELECT DISTINCT i.user_phone
  FROM intents i JOIN ordens_servico os ON os.restaurant_id=$1 AND os.cliente_phone=i.user_phone
    AND os.criado_em >= i.first_intent AND os.criado_em < $3
    AND os.status IN ('proposta_enviada','entrada_paga','confirmado','realizado')
), outcomes AS (
  SELECT i.user_phone,
    bool_or(r.status IN ('confirmada','realizada','concluida','no_show')) AS confirmed_or_outcome,
    bool_or(r.status IN ('realizada','concluida')) AS attended,
    bool_or(r.status='no_show') AS no_show
  FROM intents i
  JOIN reservas r ON r.cliente_phone=i.user_phone AND r.restaurant_id=$1
    AND r.criado_em >= i.first_intent AND r.criado_em < $3
  GROUP BY i.user_phone
)
SELECT count(*) AS contatos_com_conversa,
  coalesce(sum(c.messages),0) AS mensagens_inbound,
  count(*) FILTER (WHERE c.has_ctwa) AS contatos_com_ctwa,
  count(i.user_phone) AS contatos_com_intencao_reserva_ou_evento,
  count(p.user_phone) AS contatos_com_proposta_registrada,
  count(o.user_phone) AS contatos_com_reserva_registrada,
  count(*) FILTER (WHERE o.confirmed_or_outcome) AS contatos_com_confirmacao_ou_desfecho,
  count(*) FILTER (WHERE o.attended) AS contatos_com_reserva_realizada,
  count(*) FILTER (WHERE o.no_show) AS contatos_com_no_show
FROM conversations_in_period c
LEFT JOIN intents i ON i.user_phone=c.user_phone
LEFT JOIN proposals p ON p.user_phone=c.user_phone
LEFT JOIN outcomes o ON o.user_phone=c.user_phone
"""

RESERVATIONS_SQL = """
SELECT count(*) AS criadas,
  count(*) FILTER (WHERE status='pendente') AS pendentes,
  count(*) FILTER (WHERE status='confirmada') AS confirmadas,
  count(*) FILTER (WHERE status IN ('realizada','concluida')) AS realizadas,
  count(*) FILTER (WHERE status='no_show') AS no_show,
  count(*) FILTER (WHERE status='cancelada') AS canceladas,
  count(*) FILTER (WHERE ctwa_clid IS NOT NULL) AS com_ctwa,
  count(*) FILTER (WHERE pagamento_status='pago') AS pagamentos_marcados_pagos,
  count(*) FILTER (WHERE pagamento_status='pago' AND pagamento_valor IS NULL) AS pagamentos_sem_valor,
  sum(pagamento_valor) FILTER (WHERE pagamento_status='pago') AS valor_pagamentos_registrados_brl
FROM reservas WHERE restaurant_id=$1 AND criado_em >= $2 AND criado_em < $3
"""

COST_SQL = """
SELECT modelo_observado, tarifa_versao,
  count(*) AS turnos,
  count(*) FILTER (WHERE custo_status='complete' AND custo_total_usd IS NOT NULL) AS turnos_custo_completo,
  sum(custo_total_usd) FILTER (WHERE custo_status='complete') AS custo_observado_usd,
  sum(custo_usd) AS custo_legacy_sem_cache_usd,
  sum(tokens_input) AS tokens_input, sum(tokens_output) AS tokens_output,
  sum(tokens_cache_creation) AS tokens_cache_creation,
  sum(tokens_cache_read) AS tokens_cache_read,
  sum(custo_input_usd) AS custo_input_usd, sum(custo_output_usd) AS custo_output_usd,
  sum(custo_cache_write_5m_usd) AS custo_cache_write_5m_usd,
  sum(custo_cache_write_1h_usd) AS custo_cache_write_1h_usd,
  sum(custo_cache_read_usd) AS custo_cache_read_usd
FROM serena_metrics WHERE restaurant_id=$1 AND horario_conversa >= $2 AND horario_conversa < $3
GROUP BY modelo_observado,tarifa_versao ORDER BY modelo_observado NULLS LAST,tarifa_versao NULLS LAST
"""

COVERAGE_SQL = """
WITH inbound AS (
  SELECT user_phone, source_message_sid
  FROM conversations
  WHERE restaurant_id=$1 AND role='user' AND created_at >= $2 AND created_at < $3
), metrics AS (
  SELECT user_phone, source_message_sid, custo_status, custo_total_usd
  FROM serena_metrics
  WHERE restaurant_id=$1 AND horario_conversa >= $2 AND horario_conversa < $3
)
SELECT
  (SELECT count(*) FROM inbound) AS mensagens_inbound,
  (SELECT count(DISTINCT user_phone) FROM inbound) AS contatos_inbound,
  (SELECT count(*) FROM inbound WHERE NULLIF(user_phone,'') IS NULL) AS mensagens_sem_telefone,
  (SELECT count(*) FROM inbound WHERE NULLIF(source_message_sid,'') IS NULL) AS mensagens_sem_sid,
  (SELECT count(*) FROM inbound c WHERE EXISTS (
    SELECT 1 FROM metrics m WHERE m.user_phone=c.user_phone
      AND m.source_message_sid=c.source_message_sid
      AND NULLIF(c.source_message_sid,'') IS NOT NULL
  )) AS mensagens_com_metricas,
  (SELECT count(*) FROM metrics) AS metricas,
  (SELECT count(*) FROM metrics WHERE custo_status IS DISTINCT FROM 'complete'
    OR custo_total_usd IS NULL OR custo_total_usd < 0) AS metricas_sem_custo_completo,
  (SELECT count(*) FROM metrics m WHERE NOT EXISTS (
    SELECT 1 FROM inbound c WHERE c.user_phone=m.user_phone
      AND c.source_message_sid=m.source_message_sid
      AND NULLIF(m.source_message_sid,'') IS NOT NULL
  )) AS metricas_sem_vinculo_inbound_periodo
"""

PROMPT_COST_SQL = """
SELECT m.prompt_versao_id, p.versao, (p.id IS NOT NULL) AS versao_resolvida,
  count(*) AS turnos, count(DISTINCT m.user_phone) AS contatos_com_metricas,
  count(*) FILTER (WHERE m.intencao_detectada IN ('reserva_nova','evento')) AS turnos_com_intencao,
  count(DISTINCT m.user_phone) FILTER (
    WHERE m.intencao_detectada IN ('reserva_nova','evento')) AS contatos_com_intencao,
  count(*) FILTER (WHERE m.custo_status='complete' AND m.custo_total_usd IS NOT NULL) AS turnos_custo_completo,
  sum(m.custo_total_usd) FILTER (WHERE m.custo_status='complete') AS custo_observado_usd,
  sum(m.custo_usd) AS custo_legacy_sem_cache_usd,
  array_agg(DISTINCT m.modelo_observado) FILTER (WHERE m.modelo_observado IS NOT NULL) AS modelos_observados
FROM serena_metrics m
LEFT JOIN serena_prompt_versions p ON p.id=m.prompt_versao_id AND p.restaurant_id=m.restaurant_id
WHERE m.restaurant_id=$1 AND m.horario_conversa >= $2 AND m.horario_conversa < $3
GROUP BY m.prompt_versao_id,p.id,p.versao
ORDER BY m.prompt_versao_id NULLS LAST
"""


def _coverage(raw: dict) -> dict:
    """Coverage of persisted main-agent metrics, never of a complete provider bill."""
    result = dict(raw)
    inbound = result["mensagens_inbound"]
    result["mensagens_sem_metricas"] = inbound - result["mensagens_com_metricas"]
    complete = bool(inbound and result["contatos_inbound"] and result["metricas"]
                    and not result["mensagens_sem_metricas"] and not result["mensagens_sem_sid"]
                    and not result["mensagens_sem_telefone"]
                    and not result["metricas_sem_custo_completo"]
                    and not result["metricas_sem_vinculo_inbound_periodo"])
    result["status"] = "complete" if complete else "incomplete" if inbound or result["metricas"] else "no_data"
    result["inbound_com_metricas_pct"] = round(result["mensagens_com_metricas"] * 100 / inbound, 2) if inbound else None
    return result


def _numbers(row):
    from decimal import Decimal
    return {key: float(value) if isinstance(value, Decimal) else value for key, value in dict(row).items()}


async def build_report(restaurant_id: str, start: date, end: date, *, database_pool=None) -> dict:
    """start inclusive, end exclusive BRT dates. Outcomes use current stored status."""
    if not restaurant_id or not start < end or (end - start).days > 366:
        raise ValueError("Informe unidade e período de 1 a 366 dias, com fim exclusivo.")
    if database_pool is None:
        import database as db
        database_pool = db.pool()
    first = datetime.combine(start, time.min, tzinfo=TIMEZONE)
    last = datetime.combine(end, time.min, tzinfo=TIMEZONE)
    async with database_pool.acquire() as connection:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            business = await connection.fetchrow("SELECT nome,nome_agente FROM restaurants WHERE id=$1", restaurant_id)
            if not business:
                raise LookupError("Unidade não encontrada")
            funnel = _numbers(await connection.fetchrow(FUNNEL_SQL, restaurant_id, first, last))
            reservations = _numbers(await connection.fetchrow(RESERVATIONS_SQL, restaurant_id, first, last))
            costs = [_numbers(row) for row in await connection.fetch(COST_SQL, restaurant_id, first, last)]
            coverage = _coverage(_numbers(await connection.fetchrow(COVERAGE_SQL, restaurant_id, first, last)))
            prompt_costs = [_numbers(row) for row in await connection.fetch(PROMPT_COST_SQL, restaurant_id, first, last)]
            losses = [_numbers(row) for row in await connection.fetch("""
                SELECT loss_reason AS motivo,count(*) AS eventos,count(DISTINCT contact_id) AS contatos
                FROM contact_stage_events WHERE restaurant_id=$1
                  AND occurred_at >= $2 AND occurred_at < $3
                  AND event_type='stage_changed' AND new_stage IN ('perdido','Inativo')
                GROUP BY loss_reason ORDER BY count(*) DESC,loss_reason
            """, restaurant_id, first, last)]
    contacts = funnel["contatos_com_conversa"]
    funnel["conversao_confirmacao_ou_desfecho_pct"] = (
        round(funnel["contatos_com_confirmacao_ou_desfecho"] * 100 / contacts, 2) if contacts else None)
    intents = funnel["contatos_com_intencao_reserva_ou_evento"]
    funnel["conversao_intencao_para_confirmacao_pct"] = (
        round(funnel["contatos_com_confirmacao_ou_desfecho"] * 100 / intents, 2) if intents else None)
    observed = [item["custo_observado_usd"] for item in costs if item["custo_observado_usd"] is not None]
    total_observed = round(sum(observed), 10) if observed else None
    per_contact = (round(total_observed / coverage["contatos_inbound"], 10)
                   if coverage["status"] == "complete" and total_observed is not None else None)
    return {
        "report_version": VERSION, "restaurant_id": restaurant_id,
        "unidade": dict(business), "perdas_registradas_no_periodo": losses,
        "periodo": {"inicio_inclusivo": start.isoformat(), "fim_exclusivo": end.isoformat(), "timezone": str(TIMEZONE)},
        "funil_por_contato": funnel, "reservas_criadas_no_periodo_status_atual": reservations,
        "custo_llm": {"moeda": "USD", "por_modelo_observado": costs,
                     "total_observado_usd": total_observed,
                     "custo_por_contato_usd": per_contact, "cobertura": coverage,
                     "por_prompt_versao": prompt_costs,
                     "turnos_sem_custo_completo": sum(item["turnos"] - item["turnos_custo_completo"] for item in costs)},
        "receita_realizada_brl": None, "custo_twilio_usd": None, "roi": None,
        "definicoes": {
            "conversa": "Um contato com ao menos uma mensagem inbound no período e unidade. Não representa sessão de 24h.",
            "intencao": "Classificação existente reserva_nova/evento. Usa horário da mensagem ligada pelo SID; sem esse vínculo, horário da métrica. Após primeira mensagem do contato no período.",
            "proposta": "Contato com ordem de serviço registrada após intenção no período, em proposta_enviada, entrada_paga, confirmado ou realizado. Registro não comprova envio nem leitura da proposta; não é etapa obrigatória para reserva de mesa.",
            "confirmacao_ou_desfecho": "Reserva criada após a intenção e antes do fim; status atual confirmada, realizada, concluida ou no_show. Este relatório usa o estado atual, não reconstitui a data de confirmação.",
            "perdas": "Novas transições explícitas para perdido no período; cada reabertura e nova perda pode produzir outro evento. Sem backfill de eventos anteriores à implantação.",
            "persona": "Nome em unidade é a configuração atual. por_prompt_versao usa apenas prompt_versao_id gravado na métrica e versão associada à mesma unidade; versão ausente/inválida fica sem rótulo histórico.",
            "custo_por_contato": "Custo observado do agente principal dividido por contatos inbound distintos da mesma unidade/período, somente com cobertura integral: cada inbound ligado por SID a métrica do período, todos custos completos e nenhuma métrica sem inbound correspondente. Handoff sem métrica, falha ou ausência de SID bloqueiam a média; não são custo zero. Inclui todas as tentativas instrumentadas do mesmo SID.",
            "por_prompt_versao": "Agrupa turnos, contatos, intenções e custo pelas versões registradas nas métricas. Contato pode aparecer em mais de uma versão; não somar contatos entre grupos. Não atribui reservas/receita a uma versão por aproximação temporal ou pelo nome atual da persona.",
            "desfechos": "Status atual das reservas criadas no período, não quantidade de visitas ocorridas no período. Concluida legado conta como realizada. Um contato pode ter mais de um desfecho.",
            "atribuicao": "Último referral não vazio da mesma unidade e telefone nos 7 dias anteriores à criação. Snapshot sem retroatividade.",
        },
        "lacunas": [
            "Histórico de transições começa na implantação de 17/09/2026. Este relatório usa status atuais e não reconstrói estados de períodos anteriores.",
            "Pagamentos registrados de reservas não são faturamento conciliado; sem conciliação com PDV/OS, receita realizada e ROI permanecem nulos.",
            "Custos Twilio não foram coletados; não estimar nem tratar como zero.",
            "Custos novos cobrem turnos gravados do agente principal com usage/modelo observados. Falhas antes da gravação, classificação de handoff, relatório LLM e outras integrações ainda não estão neste custo.",
            "Métricas históricas sem cache/modelo são apresentadas como legacy, sem recalcular retroativamente.",
            "Cobertura completa significa vínculo entre inbound e métricas persistidas, não completude de faturamento ou prova de que nenhuma chamada ao provedor deixou de ser gravada.",
            "CTWA e ligação de intenção dependem de instrumentação; ausência não prova origem orgânica nem ausência de intenção.",
            "Sem SID vinculado, a intenção usa horário da métrica e pode omitir reserva criada antes da gravação dessa métrica.",
        ],
    }


def create_router(auth_dependency):
    """Inject the application's existing privileged dependency; no new auth scheme."""
    from fastapi import APIRouter, Depends, HTTPException, Query
    router = APIRouter(dependencies=[Depends(auth_dependency)])

    @router.get("/api/restaurants/{restaurant_id}/reports/commercial")
    async def report(restaurant_id: str, inicio: date = Query(...), fim: date = Query(...)):
        try:
            return await build_report(restaurant_id, inicio, fim)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
    return router
