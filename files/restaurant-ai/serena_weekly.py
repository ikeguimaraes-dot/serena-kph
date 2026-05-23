"""
Hotfix 4 — Geração de relatório semanal da Serena.

Função única `generate_weekly_report()` que:
  1. Pega snapshot da última semana (overview + handoffs + fricções + custo + intents)
  2. Pede análise executiva ao Claude
  3. Persiste em serena_weekly_reports
  4. Manda email (se RESEND_API_KEY + WEEKLY_REPORT_EMAIL setados) — best-effort

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
_RECIPIENT_ENV = "WEEKLY_REPORT_EMAIL"


async def generate_weekly_report(dias: int = 7) -> dict:
    """Gera, persiste e (best-effort) notifica por email o relatório semanal."""
    import anthropic

    end = date.today()
    start = end - timedelta(days=dias)

    overview = await db.serena_overview(dias)
    cats = await db.serena_handoffs_categorizados(dias)
    friccoes = await db.serena_friccoes(dias, limit=20)
    custo = await db.serena_custo(dias)
    intents = await db.serena_intents(dias)

    payload = {
        "overview": overview, "handoffs": cats, "friccoes": friccoes,
        "custo": custo, "intents": intents,
    }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""Você está revisando o desempenho semanal da Serena (concierge IA do Madonna Cucina).
Gere um relatório executivo curto em PT-BR com:

1. **Highlights** (2–3 bullets)
2. **Problemas detectados** (motivos de handoff recorrentes, fricções)
3. **3 sugestões de ajuste no system prompt** — cada uma com:
   - O que mudar
   - Por quê (qual problema isso resolve)
   - Texto sugerido para inserir/substituir no prompt

Dados:
{json.dumps(payload, default=str, ensure_ascii=False, indent=2)}
"""
    resp = await asyncio.to_thread(
        client.messages.create,
        model="claude-sonnet-4-5", max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))

    report = {"summary": text, "data": payload}
    rid = await db.insert_weekly_report(start, end, overview.get("total_mensagens", 0), report)

    # Email best-effort. Falha não derruba a geração.
    _maybe_send_email(rid=rid, start=start, end=end, summary=text, overview=overview)

    return {"id": rid, "semana_inicio": str(start), "semana_fim": str(end), "summary": text}


def _maybe_send_email(*, rid: int, start: date, end: date, summary: str, overview: dict) -> None:
    to = os.environ.get(_RECIPIENT_ENV, "").strip()
    if not to:
        print(f"[WEEKLY] {_RECIPIENT_ENV} não setado — email skipado (rid={rid})")
        return

    painel = os.environ.get("PAINEL_URL", _PAINEL_URL_DEFAULT).rstrip("/")
    link = f"{painel}/admin/serena?tab=weekly#r{rid}"

    summary_html = _markdown_to_html(summary)
    total_msgs = overview.get("total_mensagens", "—")

    html = f"""<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222;line-height:1.55;max-width:640px;margin:0 auto;padding:24px">
  <h1 style="font-size:20px;margin:0 0 8px">Relatório semanal · Serena</h1>
  <div style="color:#888;font-size:13px;margin-bottom:20px">{start} → {end} · {total_msgs} mensagens</div>
  <div style="border-left:3px solid #D4A574;padding:8px 16px;background:#fafafa">{summary_html}</div>
  <p style="margin-top:24px"><a href="{link}" style="color:#D4A574;text-decoration:none;font-weight:600">Abrir no painel →</a></p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
  <div style="color:#aaa;font-size:11px">Gerado automaticamente toda segunda 09h BRT. Para parar de receber, remova WEEKLY_REPORT_EMAIL no Railway.</div>
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
        # fallback mínimo se a dep não estiver instalada
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
