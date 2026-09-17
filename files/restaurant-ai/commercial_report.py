"""Deterministic, tenant-scoped commercial report. No LLM, sends, or writes."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

VERSION = "commercial-cohort-v1"
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
  count(*) FILTER (WHERE o.confirmed_or_outcome) AS contatos_com_confirmacao_ou_desfecho,
  count(*) FILTER (WHERE o.attended) AS contatos_com_reserva_realizada,
  count(*) FILTER (WHERE o.no_show) AS contatos_com_no_show
FROM conversations_in_period c
LEFT JOIN intents i ON i.user_phone=c.user_phone
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
            if not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM restaurants WHERE id=$1)", restaurant_id):
                raise LookupError("Unidade não encontrada")
            funnel = _numbers(await connection.fetchrow(FUNNEL_SQL, restaurant_id, first, last))
            reservations = _numbers(await connection.fetchrow(RESERVATIONS_SQL, restaurant_id, first, last))
            costs = [_numbers(row) for row in await connection.fetch(COST_SQL, restaurant_id, first, last)]
    contacts = funnel["contatos_com_conversa"]
    funnel["conversao_confirmacao_ou_desfecho_pct"] = (
        round(funnel["contatos_com_confirmacao_ou_desfecho"] * 100 / contacts, 2) if contacts else None)
    observed = [item["custo_observado_usd"] for item in costs if item["custo_observado_usd"] is not None]
    return {
        "report_version": VERSION, "restaurant_id": restaurant_id,
        "periodo": {"inicio_inclusivo": start.isoformat(), "fim_exclusivo": end.isoformat(), "timezone": str(TIMEZONE)},
        "funil_por_contato": funnel, "reservas_criadas_no_periodo_status_atual": reservations,
        "custo_llm": {"moeda": "USD", "por_modelo_observado": costs,
                     "total_observado_usd": round(sum(observed), 10) if observed else None,
                     "turnos_sem_custo_completo": sum(item["turnos"] - item["turnos_custo_completo"] for item in costs)},
        "receita_realizada_brl": None, "custo_twilio_usd": None, "roi": None,
        "definicoes": {
            "conversa": "Um contato com ao menos uma mensagem inbound no período e unidade. Não representa sessão de 24h.",
            "intencao": "Classificação existente reserva_nova/evento. Usa horário da mensagem ligada pelo SID; sem esse vínculo, horário da métrica. Após primeira mensagem do contato no período.",
            "confirmacao_ou_desfecho": "Reserva criada após a intenção e antes do fim; status atual confirmada, realizada, concluida ou no_show. É proxy, pois não há histórico de transições.",
            "desfechos": "Status atual das reservas criadas no período, não quantidade de visitas ocorridas no período. Concluida legado conta como realizada. Um contato pode ter mais de um desfecho.",
            "atribuicao": "Último referral não vazio da mesma unidade e telefone nos 7 dias anteriores à criação. Snapshot sem retroatividade.",
        },
        "lacunas": [
            "Sem histórico de transições, não reconstituir confirmação anterior de reservas canceladas nem status em uma data passada.",
            "Pagamentos registrados de reservas não são faturamento conciliado; sem conciliação com PDV/OS, receita realizada e ROI permanecem nulos.",
            "Custos Twilio não foram coletados; não estimar nem tratar como zero.",
            "Custos novos cobrem turnos gravados do agente principal com usage/modelo observados. Falhas antes da gravação, classificação de handoff, relatório LLM e outras integrações ainda não estão neste custo.",
            "Métricas históricas sem cache/modelo são apresentadas como legacy, sem recalcular retroativamente.",
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
