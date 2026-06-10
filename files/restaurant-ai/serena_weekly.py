"""
Sprint 10 — Relatório semanal comercial da Serena.

Reúne KPIs operacionais + comerciais por restaurante:
  - Conversas, handoffs, fricções, intents, custo
  - Receita da semana (reservas pagas + OS realizadas)
  - Pipeline OS aberto (valor total)
  - Top 5 contatos por LTV
  - Taxa de conversão (leads → reservas confirmadas)
  - SLA de handoff (TMA + taxa dentro do SLA)
  - NPS médio do período (se disponível)

Chamada por:
  - main.py: POST /api/serena/weekly-report (manual via painel/curl)
  - cron interno (APScheduler em main.py lifespan, segunda 09h BRT)
"""

import os
import json
import asyncio
from datetime import date, timedelta

import database as db
import email_gateway


_PAINEL_URL_DEFAULT = "https://madonna-painel.vercel.app"
_RECIPIENT_ENV      = "WEEKLY_REPORT_EMAIL"


# ─── Coleta de dados ────────────────────────────────────────────

async def _collect_restaurant_data(rid: str, dias: int) -> dict:
    """Coleta todos os KPIs de um restaurante em paralelo."""
    (
        overview, cats, friccoes, custo, intents,
        pipeline, sla, ltv_top5, receita_semana,
    ) = await asyncio.gather(
        db.serena_overview(dias, restaurant_id=rid),
        db.serena_handoffs_categorizados(dias, restaurant_id=rid),
        db.serena_friccoes(dias, limit=10, restaurant_id=rid),
        db.serena_custo(dias, restaurant_id=rid),
        db.serena_intents(dias, restaurant_id=rid),
        db.get_pipeline_report(rid),
        db.get_handoff_sla_stats(rid),
        _get_ltv_top5(rid),
        _get_receita_semana(rid, dias),
        return_exceptions=True,
    )

    def _safe(v, fallback):
        return fallback if isinstance(v, Exception) else v

    return {
        "restaurant_id": rid,
        "overview":       _safe(overview,       {}),
        "handoffs":       _safe(cats,            []),
        "friccoes":       _safe(friccoes,        []),
        "custo":          _safe(custo,           {}),
        "intents":        _safe(intents,         []),
        "pipeline":       _safe(pipeline,        {}),
        "sla":            _safe(sla,             {}),
        "ltv_top5":       _safe(ltv_top5,        []),
        "receita_semana": _safe(receita_semana,  {}),
    }


async def _get_ltv_top5(rid: str) -> list[dict]:
    """Top 5 contatos por LTV associados ao restaurante."""
    async with db.pool().acquire() as c:
        rows = await c.fetch("""
            SELECT ct.nome, ct.sobrenome, ct.celular,
                   ct.ltv_total, ct.total_eventos
            FROM contacts ct
            WHERE ct.ltv_total > 0
              AND EXISTS (
                SELECT 1 FROM reservas r
                WHERE r.cliente_phone = ct.celular
                  AND r.restaurant_id = $1
                UNION ALL
                SELECT 1 FROM ordens_servico o
                WHERE o.cliente_phone = ct.celular
                  AND o.restaurant_id = $1
              )
            ORDER BY ct.ltv_total DESC
            LIMIT 5
        """, rid)
    return [
        {
            "nome": f"{r['nome'] or ''} {r['sobrenome'] or ''}".strip() or r["celular"],
            "ltv_total": float(r["ltv_total"] or 0),
            "total_eventos": int(r["total_eventos"] or 0),
        }
        for r in rows
    ]


async def _get_receita_semana(rid: str, dias: int) -> dict:
    """Receita consolidada do período: reservas pagas + OS realizadas."""
    async with db.pool().acquire() as c:
        res = await c.fetchrow("""
            SELECT
                COALESCE(SUM(pagamento_valor), 0)   AS reservas_pagas,
                COUNT(*)                             AS reservas_count
            FROM reservas
            WHERE restaurant_id = $1
              AND pagamento_status = 'pago'
              AND data >= CURRENT_DATE - ($2 || ' days')::INTERVAL
        """, rid, str(dias))

        os_row = await c.fetchrow("""
            SELECT
                COALESCE(SUM(valor_total), 0)   AS os_realizadas,
                COUNT(*)                         AS os_count
            FROM ordens_servico
            WHERE restaurant_id = $1
              AND status = 'realizado'
              AND data >= CURRENT_DATE - ($2 || ' days')::INTERVAL
        """, rid, str(dias))

        conv = await c.fetchrow("""
            SELECT
                COUNT(DISTINCT m.user_phone) FILTER (WHERE m.role = 'user')     AS leads,
                COUNT(DISTINCT r.cliente_phone)                                  AS convertidos
            FROM messages m
            LEFT JOIN reservas r
              ON r.cliente_phone = m.user_phone
              AND r.restaurant_id = $1
              AND r.status IN ('confirmada','realizada')
              AND r.data >= CURRENT_DATE - ($2 || ' days')::INTERVAL
            WHERE m.restaurant_id = $1
              AND m.created_at >= NOW() - ($2 || ' days')::INTERVAL
        """, rid, str(dias))

    leads      = int(conv["leads"] or 0)
    convert    = int(conv["convertidos"] or 0)
    taxa_conv  = round((convert / leads * 100) if leads > 0 else 0, 1)

    return {
        "reservas_pagas_brl": round(float(res["reservas_pagas"] or 0), 2),
        "reservas_count":     int(res["reservas_count"] or 0),
        "os_realizadas_brl":  round(float(os_row["os_realizadas"] or 0), 2),
        "os_count":           int(os_row["os_count"] or 0),
        "total_brl":          round(float(res["reservas_pagas"] or 0) + float(os_row["os_realizadas"] or 0), 2),
        "taxa_conversao_pct": taxa_conv,
        "leads":              leads,
        "convertidos":        convert,
    }


# ─── Geração do relatório ────────────────────────────────────────

async def generate_weekly_report(dias: int = 7) -> dict:
    """Gera, persiste e (best-effort) notifica por email o relatório semanal."""
    import anthropic

    end   = date.today()
    start = end - timedelta(days=dias)

    # Coleta dados de todos os restaurantes ativos
    restaurants = await db.get_all_restaurants()
    rids = [r["id"] for r in restaurants] if restaurants else ["madonna_cucina"]

    all_data = await asyncio.gather(*[_collect_restaurant_data(rid, dias) for rid in rids])

    # Para compatibilidade com o schema existente, usa o primeiro restaurante como overview
    primary = all_data[0] if all_data else {}
    overview = primary.get("overview", {})

    payload = {
        "periodo": {"inicio": str(start), "fim": str(end), "dias": dias},
        "restaurantes": list(all_data),
    }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = _build_prompt(payload)

    resp = await asyncio.to_thread(
        client.messages.create,
        model="claude-sonnet-4-6", max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))

    report = {"summary": text, "data": payload}
    rid = await db.insert_weekly_report(start, end, overview.get("total_mensagens", 0), report)

    _maybe_send_email(rid=rid, start=start, end=end, summary=text,
                      overview=overview, all_data=list(all_data))

    return {"id": rid, "semana_inicio": str(start), "semana_fim": str(end), "summary": text}


def _build_prompt(payload: dict) -> str:
    rests = payload.get("restaurantes", [])
    periodo = payload.get("periodo", {})

    # Monta resumo compacto para o prompt
    resumos = []
    for r in rests:
        rid = r.get("restaurant_id", "?")
        ov  = r.get("overview", {})
        rec = r.get("receita_semana", {})
        pip = r.get("pipeline", {}).get("resumo", {})
        sla = r.get("sla", {})
        top5 = r.get("ltv_top5", [])

        resumos.append(f"""
### {rid}
- Mensagens: {ov.get('total_mensagens','—')} | Sessões: {ov.get('total_sessions','—')}
- Handoffs: {ov.get('handoffs_abertos','—')} abertos | {ov.get('taxa_resolucao_pct','—')}% resolvidos
- Receita semana: R${rec.get('total_brl',0):,.0f} (reservas: R${rec.get('reservas_pagas_brl',0):,.0f} + OS: R${rec.get('os_realizadas_brl',0):,.0f})
- Taxa de conversão: {rec.get('taxa_conversao_pct',0)}% ({rec.get('convertidos',0)}/{rec.get('leads',0)} leads)
- Pipeline aberto: R${pip.get('pipeline_aberto_brl',0):,.0f} | OS ativas: {pip.get('os_ativas',0)}
- SLA: TMA {sla.get('tma_minutos',0):.0f}min | taxa {sla.get('taxa_sla_pct',0)}% | vencidos {sla.get('vencidos',0)}
- Top LTV: {', '.join(f"{c['nome']} R${c['ltv_total']:,.0f}" for c in top5[:3]) or '—'}
""")

    return f"""Você é o analista de inteligência da Serena, IA concierge de restaurantes premium.
Gere um relatório executivo semanal em PT-BR ({periodo.get('inicio')} → {periodo.get('fim')}).

Estrutura obrigatória:

## Visão Geral
- 2–3 bullets com os principais números do período

## Performance Comercial
- Receita consolidada e comparação qualitativa (crescimento/queda)
- Pipeline em aberto: oportunidades e riscos
- Taxa de conversão: análise e benchmark esperado (>15%)
- Top LTV: mencione os 3 primeiros clientes (use apenas nome/apelido)

## Atendimento & SLA
- TMA vs meta (<2h)
- Handoffs vencidos: urgência se > 0
- Principais motivos de handoff e fricções

## Ações Prioritárias (máx. 3)
Para cada ação:
- O que fazer
- Por quê (dado que suporta)
- Prazo sugerido

Dados:
{''.join(resumos)}

Dados completos (JSON):
{json.dumps(payload, default=str, ensure_ascii=False, indent=1)[:6000]}
"""


# ─── Email ──────────────────────────────────────────────────────

def _maybe_send_email(
    *, rid: int, start: date, end: date,
    summary: str, overview: dict,
    all_data: list,
) -> None:
    to = os.environ.get(_RECIPIENT_ENV, "").strip()
    if not to:
        print(f"[WEEKLY] {_RECIPIENT_ENV} não setado — email skipado (rid={rid})")
        return

    painel = os.environ.get("PAINEL_URL", _PAINEL_URL_DEFAULT).rstrip("/")
    link   = f"{painel}/admin/serena?tab=weekly#r{rid}"

    summary_html  = _markdown_to_html(summary)
    total_msgs    = overview.get("total_mensagens", "—")

    # Mini tabela por restaurante
    rows_html = ""
    for r in all_data:
        rid_name = r.get("restaurant_id", "?")
        rec      = r.get("receita_semana", {})
        sla      = r.get("sla", {})
        pip      = r.get("pipeline", {}).get("resumo", {})
        rows_html += f"""
        <tr>
          <td style="padding:6px 8px;font-weight:600">{rid_name}</td>
          <td style="padding:6px 8px;text-align:right">R${rec.get('total_brl',0):,.0f}</td>
          <td style="padding:6px 8px;text-align:right">{rec.get('taxa_conversao_pct',0)}%</td>
          <td style="padding:6px 8px;text-align:right">R${pip.get('pipeline_aberto_brl',0):,.0f}</td>
          <td style="padding:6px 8px;text-align:right">{sla.get('tma_minutos',0):.0f} min</td>
          <td style="padding:6px 8px;text-align:right;color:{'#EF4444' if (sla.get('vencidos',0) or 0) > 0 else '#22C55E'}">{sla.get('vencidos',0)}</td>
        </tr>"""

    html = f"""<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222;line-height:1.55;max-width:680px;margin:0 auto;padding:24px">
  <h1 style="font-size:20px;margin:0 0 4px">Relatório semanal · Serena</h1>
  <div style="color:#888;font-size:13px;margin-bottom:20px">{start} → {end} · {total_msgs} mensagens</div>

  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:12px">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="padding:6px 8px;text-align:left">Restaurante</th>
        <th style="padding:6px 8px;text-align:right">Receita</th>
        <th style="padding:6px 8px;text-align:right">Conversão</th>
        <th style="padding:6px 8px;text-align:right">Pipeline</th>
        <th style="padding:6px 8px;text-align:right">TMA</th>
        <th style="padding:6px 8px;text-align:right">Vencidos</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>

  <div style="border-left:3px solid #D4A574;padding:8px 16px;background:#fafafa">{summary_html}</div>
  <p style="margin-top:24px"><a href="{link}" style="color:#D4A574;text-decoration:none;font-weight:600">Abrir no painel →</a></p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
  <div style="color:#aaa;font-size:11px">Gerado automaticamente toda segunda 09h BRT. Para parar, remova {_RECIPIENT_ENV} no Railway.</div>
</body></html>"""

    email_gateway.send_email(
        to=to,
        subject=f"Serena weekly · {start} a {end}",
        html=html,
    )


def _markdown_to_html(text: str) -> str:
    try:
        import markdown as md
        return md.markdown(text, extensions=["tables", "fenced_code", "nl2br"])
    except ImportError:
        lines = text.split("\n")
        out = []
        for line in lines:
            line = line.rstrip()
            if not line.strip():
                out.append("<br>")
            else:
                escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                out.append(f"<p>{escaped}</p>")
        return "\n".join(out)
