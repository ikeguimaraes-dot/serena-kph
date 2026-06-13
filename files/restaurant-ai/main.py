"""
FastAPI — WhatsApp webhook + API REST completa para o painel.
Sprint 9: multi-restaurante, financeiro, learning machine.
"""

import os
import asyncio
import json
import xml.sax.saxutils as saxutils
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Form, HTTPException, Header, Depends, BackgroundTasks, Request, Body, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from dotenv import load_dotenv
from cachetools import TTLCache
from pydantic import BaseModel

load_dotenv()
import database as db
from agent import RestaurantAgent
from models import (
    RestaurantCreate, RestaurantUpdate, BusinessHourItem,
    MenuItemCreate, MenuItemUpdate, FaqItemCreate,
    ReservationUpdate, HandoffReply, HandoffResolve, TeamMemberCreate,
    ContactUpsert, ContactUpdate, ContactKanbanMove,
)
import notifications as notif
from email_service import (
    send_confirmacao_reserva,
    send_proposta_enviada,
    send_comprovante_pagamento,
)

# ── Onda 8 — Cache em memória ─────────────────────────────────
# /api/reports é caro (15 queries em paralelo). Cache 60s reduz pressão.
# /api/insights é mais caro ainda (heurísticas). Cache 1h.
_reports_cache = TTLCache(maxsize=64, ttl=60)
_insights_cache = TTLCache(maxsize=8, ttl=3600)
_serena_metrics_cache = TTLCache(maxsize=32, ttl=120)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    _scheduler = None
    try:
        _scheduler = _start_weekly_cron()
    except Exception as e:
        print(f"[CRON] startup falhou (app continua): {e!r}")
    try:
        yield
    finally:
        if _scheduler is not None:
            try: _scheduler.shutdown(wait=False)
            except Exception: pass
        await db.close_db()


def _start_weekly_cron():
    """Hotfix 4 — agenda relatório semanal toda segunda 09h BRT.

    APScheduler in-process (single dep, single instance). Se SCALE > 1 no
    Railway algum dia, migrar pra Railway Cron Service ou lock distribuído.

    DISABLE_WEEKLY_CRON=1 no env desliga sem precisar redeploy.
    """
    if os.environ.get("DISABLE_WEEKLY_CRON") == "1":
        print("[CRON] DISABLE_WEEKLY_CRON=1 — agendamento desligado")
        return None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("[CRON] apscheduler não instalado — `pip install apscheduler`")
        return None

    import serena_weekly

    async def job():
        print("[CRON] weekly-report disparado")
        try:
            r = await serena_weekly.generate_weekly_report()
            print(f"[CRON] weekly-report ok rid={r.get('id')}")
        except Exception as e:
            print(f"[CRON] weekly-report FALHOU: {e!r}")

    sch = AsyncIOScheduler(timezone="America/Sao_Paulo")
    sch.add_job(
        job,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="serena_weekly_report",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,  # se restart bater no horário, ainda dispara em até 1h
    )
    sch.start()
    print("[CRON] weekly-report agendado: segunda 09h00 America/Sao_Paulo")
    return sch

app = FastAPI(title="Restaurant AI — API", lifespan=lifespan)

# CORS — whitelist em produção (env CORS_ORIGINS=comma,separated). Default seguro.
_default_origins = "https://madonna-painel.vercel.app,https://madonna-cucina-painel.vercel.app,http://localhost:3000"
_origins_raw = os.environ.get("CORS_ORIGINS", _default_origins)
allow_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
agent = RestaurantAgent()


# ── Auth: header secret simples para endpoints sensíveis ──────
def require_admin(x_admin_secret: Optional[str] = Header(None)):
    secret = os.environ.get("ADMIN_SECRET")
    if not secret:
        raise HTTPException(503, "Servidor mal configurado: ADMIN_SECRET ausente")
    if x_admin_secret != secret:
        raise HTTPException(403, "Acesso negado")
    return True


# ── Twilio HMAC — valida autenticidade do webhook ─────────────
async def validate_twilio_signature(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None),
):
    """Valida X-Twilio-Signature com HMAC-SHA1.

    Se TWILIO_AUTH_TOKEN não estiver configurado, loga aviso e passa
    (compatibilidade com ambiente local / testes).
    Retorna 403 se a assinatura for inválida.
    """
    from twilio.request_validator import RequestValidator

    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token or auth_token.startswith("..."):
        is_prod = os.environ.get("RAILWAY_ENVIRONMENT", "") == "production"
        if is_prod:
            raise HTTPException(status_code=503, detail="TWILIO_AUTH_TOKEN não configurado em produção")
        print("[WEBHOOK] TWILIO_AUTH_TOKEN ausente — validação HMAC ignorada (dev/local)")
        return

    if not x_twilio_signature:
        print("[WEBHOOK] Rejeitado: X-Twilio-Signature ausente")
        raise HTTPException(403, "X-Twilio-Signature ausente")

    # Railway executa atrás de proxy: reconstruir URL pública com headers injetados
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host  = request.headers.get("host") or request.url.netloc
    path  = request.url.path
    query = request.url.query
    url   = f"{proto}://{host}{path}" + (f"?{query}" if query else "")

    # Lê os form params para a assinatura (Starlette cacheia o body após o primeiro read)
    form   = await request.form()
    params = dict(form.multi_items())

    validator = RequestValidator(auth_token)
    if not validator.validate(url, params, x_twilio_signature):
        print(f"[WEBHOOK] HMAC inválido — url={url!r} sig={x_twilio_signature!r}")
        raise HTTPException(403, "Assinatura Twilio inválida")

    print(f"[WEBHOOK] HMAC válido — url={url!r}")


# ════════════════════════════════════════════════════════════════
# WHATSAPP WEBHOOK
# ════════════════════════════════════════════════════════════════

MAX_MSG_LEN = 2000

async def _tentar_capturar_nps(telefone: str, texto: str) -> bool:
    """Retorna True se a mensagem era um NPS (1-10) e foi capturada."""
    import re as _re
    if not _re.fullmatch(r'[1-9]|10', texto.strip()):
        return False
    nota = int(texto.strip())
    # Busca OS com D+3 enviado, sem NPS ainda, desse telefone
    query = """
        SELECT os.id FROM ordens_servico os
        JOIN contacts c ON c.id = os.contact_id
        WHERE c.telefone = $1
          AND os.regua_d3_enviado_em IS NOT NULL
          AND os.nps_score IS NULL
        ORDER BY os.regua_d3_enviado_em DESC
        LIMIT 1
    """
    from database import pool
    async with pool().acquire() as c:
        row = await c.fetchrow(query, telefone)
    if row:
        await db.registrar_nps(row["id"], nota)
        return True
    return False


async def _process_and_reply(user_phone: str, restaurant_phone: str, message: str, profile_name: str):
    """Processa mensagem via LLM e envia resposta via Twilio outbound.

    Roda em background para não bloquear o webhook além dos 15s de timeout do Twilio.
    None indica conversa em handoff — equipe já notificada pelo agent.process.
    """
    try:
        # Captura NPS antes de passar para o agente
        if await _tentar_capturar_nps(user_phone, message):
            nota = int(message.strip())
            if nota >= 9:
                resposta_nps = "Que incrível! 🌟 Obrigado pela sua avaliação — seu feedback é muito importante para nós!"
            elif nota >= 7:
                resposta_nps = "Obrigado pelo feedback! 😊 Continuaremos trabalhando para aprimorar cada detalhe da experiência."
            else:
                resposta_nps = "Obrigado por nos contar. 🙏 Vamos usar seu feedback para melhorar. Se quiser detalhar o que aconteceu, estamos ouvindo."
            notif.send_to_customer(restaurant_phone, user_phone, resposta_nps)
            return

        response_text = await agent.process(user_phone, restaurant_phone, message, profile_name=profile_name)
        if response_text is None:
            return
        notif.send_to_customer(restaurant_phone, user_phone, response_text)
    except Exception as e:
        print(f"[WEBHOOK BG] erro ao processar/enviar user={user_phone!r}: {e!r}")


@app.post("/webhook/whatsapp", dependencies=[Depends(validate_twilio_signature)])
async def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    From: str = Form(...), Body: str = Form(""), To: str = Form(...),
    ProfileName: str = Form(""),
):

    print(f"[WEBHOOK] From={From!r} To={To!r} ProfileName={ProfileName!r} Body={Body!r}")
    message = Body.strip()
    if not message:
        return _twiml_ack()
    if len(message) > MAX_MSG_LEN:
        print(f"[WEBHOOK] mensagem descartada: tamanho {len(message)} > {MAX_MSG_LEN}")
        notif.send_to_customer(
            To.replace("whatsapp:", "").strip(),
            From.replace("whatsapp:", "").strip(),
            "Mensagem muito longa. Por favor, envie uma mensagem mais curta.",
        )
        return _twiml_ack()

    user_phone       = From.replace("whatsapp:", "").strip()
    restaurant_phone = To.replace("whatsapp:", "").strip()
    print(f"[WEBHOOK] user_phone={user_phone!r} restaurant_phone={restaurant_phone!r}")
    print(f"[WEBHOOK] ProfileName='{ProfileName}' user_phone='{user_phone}'")

    # Retorna imediatamente para evitar timeout do Twilio (15s).
    # O processamento LLM + envio ocorrem em background via Twilio outbound.
    background_tasks.add_task(
        _process_and_reply, user_phone, restaurant_phone, message, ProfileName
    )
    return _twiml_ack()


# ════════════════════════════════════════════════════════════════
# RESTAURANTES
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants")
async def list_restaurants():
    return await db.get_all_restaurants()

@app.post("/api/restaurants", status_code=201)
async def create_restaurant(data: RestaurantCreate):
    return await db.create_restaurant(data.model_dump())

@app.get("/api/restaurants/{rid}")
async def get_restaurant(rid: str):
    r = await db.get_restaurant(rid)
    if not r:
        raise HTTPException(404, "Restaurante não encontrado")
    return r

@app.patch("/api/restaurants/{rid}")
async def update_restaurant(rid: str, data: RestaurantUpdate):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if not await db.update_restaurant(rid, payload):
        raise HTTPException(404)
    return {"ok": True}

@app.put("/api/restaurants/{rid}/hours")
async def save_hours(rid: str, hours: list[BusinessHourItem]):
    await db.save_business_hours(rid, [h.model_dump() for h in hours])
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# CARDÁPIO
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/menu")
async def list_menu(rid: str):
    return await db.get_menu_items(rid)

@app.post("/api/restaurants/{rid}/menu", status_code=201)
async def create_menu_item(rid: str, data: MenuItemCreate):
    return await db.create_menu_item(rid, data.model_dump())

@app.patch("/api/menu/{item_id}")
async def update_menu_item(item_id: int, data: MenuItemUpdate):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if not await db.update_menu_item(item_id, payload):
        raise HTTPException(404)
    return {"ok": True}

@app.delete("/api/menu/{item_id}")
async def delete_menu_item(item_id: int):
    if not await db.delete_menu_item(item_id):
        raise HTTPException(404)
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# FAQ
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/faq")
async def list_faq(rid: str):
    return await db.get_faq_items(rid)

@app.put("/api/restaurants/{rid}/faq")
async def upsert_faq(rid: str, data: FaqItemCreate):
    return await db.upsert_faq_item(rid, data.model_dump())

@app.delete("/api/faq/{item_id}")
async def delete_faq(item_id: int):
    if not await db.delete_faq_item(item_id):
        raise HTTPException(404)
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# RESERVAS
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/reservations")
async def list_reservations(rid: str, data: Optional[str]=None, status: Optional[str]=None):
    return await db.get_reservations(rid, data, status)

@app.patch("/api/reservations/{res_id}")
async def update_reservation(res_id: str, data: ReservationUpdate):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    if not await db.update_reservation(res_id, payload):
        raise HTTPException(404)
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# HANDOFF — atendimento humano
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/handoff", dependencies=[Depends(require_admin)])
async def list_handoff(rid: str, status: Optional[str]=None):
    return await db.get_handoff_sessions(rid, status)

@app.post("/api/handoff/{hid}/reply")
async def handoff_reply(hid: int, data: HandoffReply):
    """Atendente responde pelo painel — mensagem vai via Twilio para o cliente."""
    print(f"[HANDOFF REPLY] chamado hid={hid} atendente={data.atendente_nome!r} msg={data.mensagem!r}")

    session = await db.get_handoff_by_id(hid)
    if not session:
        print(f"[HANDOFF REPLY] handoff não encontrado hid={hid}")
        raise HTTPException(404)

    restaurant = await db.get_restaurant_full(session["restaurant_id"])
    print(f"[HANDOFF REPLY] enviando Twilio from={os.environ.get('TWILIO_FROM_NUMBER')!r} to={session['user_phone']!r}")

    try:
        notif.send_to_customer(
            restaurant["whatsapp_number"],
            session["user_phone"],
            data.mensagem,
        )
        print(f"[HANDOFF REPLY] Twilio OK hid={hid}")
    except Exception as e:
        # Twilio falhou — NÃO salva msg no banco, NÃO avança status, retorna 502
        # pra o painel mostrar o erro pro operador em vez de esconder.
        print(f"[HANDOFF REPLY] Twilio FALHOU hid={hid}: {e!r}")
        raise HTTPException(502, f"Twilio não entregou a mensagem: {e}")

    await db.save_message(session["user_phone"], session["restaurant_id"],
                          "assistant", f"[{data.atendente_nome}] {data.mensagem}")
    await db.update_handoff_status(hid, "em_atendimento", data.atendente_nome)
    print(f"[HANDOFF REPLY] concluído hid={hid} twilio_ok=True")
    return {"ok": True}

@app.post("/api/handoff/{hid}/assume")
async def handoff_assume(hid: int, data: HandoffResolve):
    """Operador assume handoff (aguardando → em_atendimento) sem enviar msg."""
    session = await db.get_handoff_by_id(hid)
    if not session:
        raise HTTPException(404)
    await db.update_handoff_status(hid, "em_atendimento", data.atendente_nome)
    print(f"[HANDOFF ASSUME] hid={hid} atendente={data.atendente_nome!r}")
    return {"ok": True, "user_phone": session["user_phone"]}

@app.post("/api/handoff/{hid}/resolve")
async def handoff_resolve(hid: int, data: HandoffResolve):
    await db.update_handoff_status(hid, "resolvido", data.atendente_nome)
    return {"ok": True}


@app.post("/api/handoff/assumir")
async def assumir_conversa(data: dict):
    """Cria handoff manualmente a partir do painel, sem solicitação do cliente."""
    user_phone = data.get("user_phone")
    restaurant_id = data.get("restaurant_id")
    atendente = data.get("atendente_nome", "Atendente")
    if not user_phone or not restaurant_id:
        raise HTTPException(400, "user_phone e restaurant_id são obrigatórios")
    hid = await db.create_handoff(user_phone, restaurant_id, f"Atendimento iniciado manualmente por {atendente}")
    await db.update_handoff_status(hid, "em_atendimento", atendente)
    print(f"[HANDOFF ASSUMIR] hid={hid} user={user_phone} restaurant={restaurant_id} atendente={atendente!r}")
    return {"id": hid, "status": "em_atendimento"}


# ════════════════════════════════════════════════════════════════
# AGENDA PRÓPRIA — Reservas Serena 2.0
# ════════════════════════════════════════════════════════════════

@app.get("/api/agenda/{restaurant_id}/disponibilidade")
async def disponibilidade(restaurant_id: str, data: str, dias: int = 7):
    """Retorna disponibilidade dos próximos N dias."""
    slots = await db.get_disponibilidade_semana(restaurant_id, data, dias)
    return {"slots": slots}

@app.get("/api/agenda/{restaurant_id}/reservas")
async def listar_reservas_agenda(
    restaurant_id: str,
    data: str | None = None,
    status: str | None = None,
    limit: int = 100,
    view: str | None = None,
    data_inicio: str | None = None,
):
    from datetime import date
    # view=semana: retorna agregado de 7 dias
    if view == "semana":
        start = data_inicio or date.today().isoformat()
        rows = await db.listar_reservas_semana(restaurant_id, start)
        return rows
    target = data or date.today().isoformat()
    rows = await db.listar_reservas_por_data(restaurant_id, target, status, limit)
    return rows

@app.post("/api/agenda/{restaurant_id}/reservas", status_code=201)
async def nova_reserva(restaurant_id: str, body: dict = Body(...)):
    """Cria nova reserva. Verifica disponibilidade antes.

    turno_id é opcional — quando ausente tenta resolver via hora_inicio.
    Aceita aliases de campo: nome/cliente_nome, telefone/cliente_phone, pessoas/posicoes.
    """
    # Normaliza aliases enviados pelo curl / fontes externas
    if "nome" in body and "cliente_nome" not in body:
        body["cliente_nome"] = body.pop("nome")
    if "telefone" in body and "cliente_phone" not in body:
        body["cliente_phone"] = body.pop("telefone")
    if "pessoas" in body and "posicoes" not in body:
        body["posicoes"] = body.pop("pessoas")

    # Campos mínimos obrigatórios
    for campo in ("data", "posicoes"):
        if campo not in body:
            raise HTTPException(status_code=422, detail=f"Campo obrigatório ausente: {campo}")

    # turno_id opcional: tenta resolver via hora_inicio se não vier no body
    turno_id = body.get("turno_id")
    if not turno_id and body.get("hora_inicio"):
        from datetime import date as _date
        try:
            data_obj = _date.fromisoformat(str(body["data"]))
            # PostgreSQL EXTRACT(DOW) = 0 (Dom) … 6 (Sab); Python weekday() = 0 (Seg) … 6 (Dom)
            dia_dow = (data_obj.weekday() + 1) % 7
            turnos = await db.get_turnos(restaurant_id, dia_dow)
            hora_req = str(body["hora_inicio"])[:5]  # "19:00"
            match = next(
                (t for t in turnos if str(t.get("hora_inicio", ""))[:5] == hora_req), None
            )
            if match:
                turno_id = str(match["id"])
                body["turno_id"] = turno_id
        except Exception as _e:
            print(f"[nova_reserva] turno lookup falhou: {_e!r}")

    body["restaurant_id"] = restaurant_id

    # Verifica disponibilidade apenas se turno_id foi resolvido
    if turno_id:
        disponivel = await db.check_disponibilidade(
            restaurant_id, body["data"], turno_id, int(body["posicoes"])
        )
        if not disponivel.get("disponivel"):
            raise HTTPException(409, detail=disponivel.get("motivo", "Sem disponibilidade"))

    reserva = await db.criar_reserva(body)
    return reserva

@app.get("/api/agenda/{restaurant_id}/reservas/{reserva_id}")
async def get_reserva(restaurant_id: str, reserva_id: str):
    reserva = await db.get_reserva(reserva_id)
    if not reserva or reserva["restaurant_id"] != restaurant_id:
        raise HTTPException(404)
    return reserva

@app.get("/api/agenda/{restaurant_id}/reservas/cliente/{phone}")
async def reservas_cliente(restaurant_id: str, phone: str):
    reservas = await db.get_reservas_por_phone(restaurant_id, phone)
    return {"reservas": reservas}

@app.patch("/api/agenda/{restaurant_id}/reservas/{reserva_id}/confirmar")
async def confirmar(restaurant_id: str, reserva_id: str):
    ok = await db.confirmar_reserva(reserva_id, restaurant_id)
    if not ok:
        raise HTTPException(404, "Reserva não encontrada ou não está pendente")
    # Fire-and-forget: email de confirmação não bloqueia a resposta
    try:
        reserva_data = await db.get_reserva(reserva_id)
        if reserva_data:
            asyncio.create_task(send_confirmacao_reserva(dict(reserva_data)))
    except Exception as _e:
        print(f"[email] erro ao disparar confirmacao_reserva: {_e!r}")
    return {"ok": True}

@app.get("/api/agenda/{restaurant_id}/ocupacao")
async def ocupacao_mensal(restaurant_id: str, mes: str | None = None):
    from datetime import date
    mes = mes or date.today().strftime("%Y-%m")
    return await db.get_ocupacao_mensal(restaurant_id, mes)


@app.patch("/api/agenda/{restaurant_id}/reservas/{reserva_id}/cancelar")
async def cancelar(restaurant_id: str, reserva_id: str):
    ok = await db.cancelar_reserva(reserva_id, restaurant_id)
    if not ok:
        raise HTTPException(404, "Reserva não encontrada ou já cancelada")
    return {"ok": True}


@app.patch("/api/agenda/{restaurant_id}/reservas/{reserva_id}/status",
           dependencies=[Depends(require_admin)])
async def atualizar_status_reserva(
    restaurant_id: str,
    reserva_id: str,
    body: dict = Body(...),
):
    """Atualiza status genérico: no_show | realizada | confirmada | cancelada"""
    status = body.get("status")
    if not status:
        raise HTTPException(422, "Campo 'status' obrigatório")
    try:
        reserva = await db.atualizar_status_reserva(reserva_id, restaurant_id, status)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not reserva:
        raise HTTPException(404, "Reserva não encontrada")
    return reserva


@app.delete("/api/agenda/{restaurant_id}/reservas/{reserva_id}",
            dependencies=[Depends(require_admin)])
async def deletar_reserva(restaurant_id: str, reserva_id: str):
    """Soft delete — equivale a cancelar."""
    ok = await db.cancelar_reserva(reserva_id, restaurant_id)
    if not ok:
        raise HTTPException(404, "Reserva não encontrada ou já cancelada")
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# CONVERSAS
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/conversations", dependencies=[Depends(require_admin)])
async def list_conversations(rid: str):
    return await db.get_conversations_list(rid)

@app.get("/api/conversations/{user_phone}", dependencies=[Depends(require_admin)])
async def get_conversation(user_phone: str, rid: str):
    return await db.get_history(user_phone, rid, limit=100)


# ════════════════════════════════════════════════════════════════
# EQUIPE
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/team")
async def list_team(rid: str):
    return await db.get_team(rid)

@app.post("/api/restaurants/{rid}/team", status_code=201)
async def add_team_member(rid: str, data: TeamMemberCreate):
    return await db.create_team_member(rid, data.model_dump())


# ════════════════════════════════════════════════════════════════
# RELATÓRIOS
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/reports/overview")
async def report_overview(rid: str):
    return await db.report_overview(rid)

@app.get("/api/restaurants/{rid}/reports/reservations")
async def report_reservations(rid: str, days: int = 30):
    return await db.report_reservations_by_day(rid, days)

@app.get("/api/restaurants/{rid}/reports/peak-hours")
async def report_peak(rid: str):
    return await db.report_peak_hours(rid)

@app.get("/api/restaurants/{rid}/reports/conversion")
async def report_conversion(rid: str):
    return await db.report_conversion(rid)

@app.get("/api/reports")
async def reports_full(rid: str, days: int = 7):
    """Agregado único — cache 60s (TTLCache em memória)."""
    key = f"{rid}:{days}"
    if key in _reports_cache:
        return _reports_cache[key]
    data = await db.report_full(rid, days=days)
    _reports_cache[key] = data
    return data


# ════════════════════════════════════════════════════════════════
# CRM — CONTATOS
# ════════════════════════════════════════════════════════════════

@app.post("/api/contacts", status_code=201)
async def upsert_contact(data: ContactUpsert):
    """Cria ou atualiza contato pelo celular (upsert)."""
    return await db.upsert_contact(data.model_dump(exclude_none=False))

@app.get("/api/contacts", dependencies=[Depends(require_admin)])
async def list_contacts(
    tier: Optional[str] = None,
    estagio: Optional[str] = None,
    ocasiao: Optional[str] = None,
    tag: Optional[str] = None,
    opt_in: Optional[bool] = None,
    limit: int = 500,
):
    return await db.list_contacts(
        tier=tier, estagio=estagio, ocasiao=ocasiao,
        tag=tag, opt_in=opt_in, limit=limit,
    )

@app.get("/api/contacts/search", dependencies=[Depends(require_admin)])
async def search_contacts(q: str, limit: int = 50):
    return await db.search_contacts(q, limit=limit)

@app.get("/api/contacts/stats", dependencies=[Depends(require_admin)])
async def contact_stats():
    return await db.contact_stats()

@app.get("/api/contacts/funil-stats", dependencies=[Depends(require_admin)])
async def funil_stats():
    """KPIs do funil comercial: leads/semana, score breakdown, metas."""
    return await db.get_funil_stats()

@app.post("/api/contacts/mark-inactive", dependencies=[Depends(require_admin)])
async def contacts_mark_inactive(threshold_days: int = 45):
    """Move para 'Inativo' contatos sem visita há N+ dias. Cron-only — exige x-admin-secret."""
    affected = await db.mark_inactive_contacts(threshold_days)
    return {"affected": affected}

@app.get("/api/contacts/{celular}", dependencies=[Depends(require_admin)])
async def get_contact(celular: str):
    c = await db.get_contact(celular)
    if not c:
        raise HTTPException(404, "Contato não encontrado")
    return c

@app.get("/api/contacts/{celular}/reservations", dependencies=[Depends(require_admin)])
async def contact_reservations(celular: str, limit: int = 20):
    return await db.get_contact_reservations(celular, limit=limit)

@app.get("/api/contacts/{celular}/conversations", dependencies=[Depends(require_admin)])
async def contact_conversations(celular: str, limit: int = 100):
    return await db.get_contact_conversations(celular, limit=limit)

@app.patch("/api/contacts/{celular}")
async def patch_contact(celular: str, data: ContactUpdate):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    c = await db.update_contact(celular, payload)
    if not c:
        raise HTTPException(404)
    return c

@app.patch("/api/contacts/{celular}/kanban", dependencies=[Depends(require_admin)])
async def move_kanban(celular: str, data: ContactKanbanMove):
    try:
        c = await db.move_contact_kanban(celular, data.estagio_kanban)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not c:
        raise HTTPException(404)
    return c


@app.get("/api/contacts/{celular}/profile", dependencies=[Depends(require_admin)])
async def contact_profile(celular: str, limit: int = 50):
    """Perfil combinado: dados do contato + últimas mensagens."""
    contact = await db.get_contact(celular)
    if not contact:
        raise HTTPException(404, "Contato não encontrado")
    messages = await db.get_contact_conversations(celular, limit=limit)
    return {**contact, "messages": messages}

@app.patch("/api/handoff/{hid}/kanban")
async def handoff_kanban(hid: int, data: dict):
    """Move um handoff no kanban. stage: aguardando | em_atendimento | resolvido"""
    stage = data.get("stage")
    if not stage:
        raise HTTPException(400, "Campo 'stage' obrigatório")
    ok = await db.update_handoff_kanban(hid, stage)
    if not ok:
        raise HTTPException(400, "Stage inválido ou handoff não encontrado. Use: aguardando, em_atendimento, resolvido")
    return {"ok": True}


@app.post("/api/contacts/{phone}/retag")
async def retag_contact(phone: str, restaurant_id: str):
    """Recalcula as auto-tags de um contato manualmente."""
    async with db.pool().acquire() as c:
        await c.execute("SELECT auto_tag_contact($1, $2)", restaurant_id, phone)
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# SERENA INSTRUMENTATION (Onda 8)
# ════════════════════════════════════════════════════════════════

def _periodo_to_days(periodo: str) -> int:
    p = (periodo or "7d").lower()
    if p in ("mtd", "mes", "month"): return 31
    if p.endswith("d"):
        try: return max(1, int(p[:-1]))
        except ValueError: return 7
    return 7

@app.get("/api/serena/metrics", dependencies=[Depends(require_admin)])
async def serena_metrics(periodo: str = "7d"):
    days = _periodo_to_days(periodo)
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    key = f"overview:{days}:{rid or ''}"
    if key in _serena_metrics_cache:
        return _serena_metrics_cache[key]
    data = await db.serena_overview(days, restaurant_id=rid)
    _serena_metrics_cache[key] = data
    return data

@app.get("/api/serena/handoffs/categorizados")
async def serena_handoffs_cat(periodo: str = "30d"):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_handoffs_categorizados(_periodo_to_days(periodo), restaurant_id=rid)

@app.get("/api/serena/intencoes")
async def serena_intencoes(periodo: str = "30d"):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_intents(_periodo_to_days(periodo), restaurant_id=rid)

@app.get("/api/serena/friccoes")
async def serena_friccoes(periodo: str = "14d", limit: int = 30, offset: int = 0):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_friccoes(_periodo_to_days(periodo), limit=limit, offset=offset, restaurant_id=rid)

@app.get("/api/serena/tools/stats")
async def serena_tools(periodo: str = "30d"):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_tools_stats(_periodo_to_days(periodo), restaurant_id=rid)

@app.get("/api/serena/custo", dependencies=[Depends(require_admin)])
async def serena_custo(periodo: str = "mtd"):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_custo(_periodo_to_days(periodo), restaurant_id=rid)

@app.get("/api/serena/recent", dependencies=[Depends(require_admin)])
async def serena_recent(limit: int = 100, only_handoffs: bool = False):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_recent(limit=limit, only_handoffs=only_handoffs, restaurant_id=rid)

@app.get("/api/serena/training-export", dependencies=[Depends(require_admin)])
async def serena_training_export(formato: str = "jsonl", limit: int = 1000):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    rows = await db.export_serena_for_training(limit=limit, restaurant_id=rid)
    if formato == "json":
        return rows
    # JSONL como text/plain
    import json
    body = "\n".join(json.dumps(r, default=str) for r in rows)
    return PlainTextResponse(body, media_type="application/x-ndjson")


# ── Nurture automático (Sprint 2) ─────────────────────────────

@app.post("/api/serena/nurture", dependencies=[Depends(require_admin)])
async def serena_nurture(background_tasks: BackgroundTasks, dry_run: bool = False):
    """Roda a régua de nurture: busca leads mornos inativos há 3+ dias e envia via Twilio.

    Roda diariamente via cron externo (ex: Railway Cron ou GitHub Actions).
    dry_run=true retorna os leads sem enviar mensagens.
    """
    leads = await db.get_nurture_leads(days_inactive=3)
    if dry_run:
        return {"dry_run": True, "leads": leads, "total": len(leads)}

    restaurant = await db.get_restaurant_full(os.environ.get("AGENT_NAME", "madonna_cucina"))
    sent = []
    errors = []

    for lead in leads:
        celular = lead["celular"]
        nome = (lead["nome"] or "").split()[0] or "você"
        try:
            msg = (
                f"Oi {nome}! Ainda pensando em visitar a gente? "
                f"Temos novidades que podem te interessar — e adoraríamos ajudar a encontrar a data perfeita. "
                f"Me conta quando está pensando em vir! 😊"
            )
            background_tasks.add_task(
                notif.send_to_customer,
                restaurant["whatsapp_number"],
                celular,
                msg,
            )
            # Registra nas notas do contato
            nota = f"[Nurture automático enviado em {__import__('datetime').date.today()}]"
            notas_atuais = lead.get("notas") or ""
            await db.update_contact(celular, {"notas": f"{notas_atuais}\n{nota}".strip()})
            sent.append(celular)
        except Exception as e:
            errors.append({"celular": celular, "error": str(e)})

    return {"sent": len(sent), "errors": len(errors), "details": errors or None}


# ─── Régua pós-evento ────────────────────────────────────────────

@app.post("/api/serena/pos-evento", dependencies=[Depends(require_admin)])
async def rodar_regua_pos_evento(
    background_tasks: BackgroundTasks,
    rid: str = Query("madonna_cucina"),
):
    background_tasks.add_task(_job_regua_pos_evento, rid)
    return {"status": "job_iniciado", "restaurant_id": rid}


async def _job_regua_pos_evento(restaurant_id: str):
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone.utc)

    restaurant = await db.get_restaurant_full(restaurant_id)
    restaurant_phone = restaurant["whatsapp_number"] if restaurant else None

    os_list = await db.get_os_para_regua(restaurant_id)
    enviados: list = []

    for os_item in os_list:
        os_id     = os_item["id"]
        telefone  = os_item["telefone"]
        nome      = (os_item["contact_nome"] or "você").split()[0]
        titulo    = os_item["titulo"] or "o evento"
        realizado = os_item["evento_realizado_em"]

        if not realizado or not telefone or not restaurant_phone:
            continue

        delta = agora - realizado

        _twilio = notif._client()
        _from   = f"whatsapp:{restaurant_phone or os.environ.get('TWILIO_FROM_NUMBER', '')}"
        _to     = f"whatsapp:{telefone}"
        _vars   = json.dumps({"1": nome, "2": titulo})

        # D+1 — Agradecimento (entre 20h e 30h após o evento)
        if (
            not os_item["regua_d1_enviado_em"]
            and timedelta(hours=20) <= delta <= timedelta(hours=30)
        ):
            if _twilio:
                _twilio.messages.create(
                    from_=_from, to=_to,
                    content_sid="HX7a16cfb714c360daa4cb1dd391839f1a",
                    content_variables=_vars,
                )
            await db.marcar_regua_enviada(os_id, "d1")
            enviados.append({"os_id": os_id, "etapa": "d1"})

        # D+3 — NPS (entre 68h e 80h após o evento)
        elif (
            os_item["regua_d1_enviado_em"]
            and not os_item["regua_d3_enviado_em"]
            and timedelta(hours=68) <= delta <= timedelta(hours=80)
        ):
            if _twilio:
                _twilio.messages.create(
                    from_=_from, to=_to,
                    content_sid="HXe90e74853e6f43815ed076964f39030b",
                    content_variables=_vars,
                )
            await db.marcar_regua_enviada(os_id, "d3")
            enviados.append({"os_id": os_id, "etapa": "d3"})

        # D+7 — Fotos (entre 7d e 8d após o evento)
        elif (
            os_item["regua_d3_enviado_em"]
            and not os_item["regua_d7_enviado_em"]
            and timedelta(days=7) <= delta <= timedelta(days=8)
        ):
            if _twilio:
                _twilio.messages.create(
                    from_=_from, to=_to,
                    content_sid="HXaacf87d6d7d582ff3a26c98bd41b9637",
                    content_variables=_vars,
                )
            await db.marcar_regua_enviada(os_id, "d7")
            enviados.append({"os_id": os_id, "etapa": "d7"})

        # D+30 — Reativação (entre 30d e 32d após o evento)
        elif (
            os_item["regua_d7_enviado_em"]
            and not os_item["regua_d30_enviado_em"]
            and timedelta(days=30) <= delta <= timedelta(days=32)
        ):
            if _twilio:
                _twilio.messages.create(
                    from_=_from, to=_to,
                    content_sid="HX2f99ec2032087dc650b2e84047345048",
                    content_variables=_vars,
                )
            await db.marcar_regua_enviada(os_id, "d30")
            enviados.append({"os_id": os_id, "etapa": "d30"})

    print(f"[pos-evento] {len(enviados)} mensagens enviadas")
    return {"enviados": len(enviados)}


# ── Versionamento de prompt ────────────────────────────────────

class PromptCreate(BaseModel):
    versao: str
    prompt_completo: str
    changelog: Optional[str] = None
    ativar: bool = False
    restaurant_id: str = "madonna_cucina"  # painel gerencia Madonna; outras casas via SQL/seed

class TestMessage(BaseModel):
    message: str
    restaurant_id: Optional[str] = None  # Se None, tentará obter do AGENT_NAME ou fallback
    prompt_version_id: Optional[int] = None  # se setado, usa essa versão (mesmo inativa)
    user_phone: Optional[str] = None  # se setado, injeta contexto CRM desse contato


@app.post("/api/serena/test-message", dependencies=[Depends(require_admin)])
async def serena_test_message(data: TestMessage):
    """Roda 1 turno com a Serena SEM persistir métricas/handoff/conversation.
    Útil para validar mudanças de prompt antes de ativar.

    Se prompt_version_id for passado, usa essa versão (pode ser inativa) em vez da v ativa.
    Se user_phone for passado, injeta o bloco CONTATO ATUAL com dados reais do CRM.
    """
    rid = data.restaurant_id
    if not rid:
        agent_id = os.environ.get("AGENT_NAME")
        rid = agent_id.lower().strip() if agent_id else "madonna_cucina"
        
    restaurant = await db.get_restaurant_full(rid)
    if not restaurant:
        # Tenta buscar qualquer um ou cria em memória como fallback para testes não falharem
        restaurant = await db.get_restaurant_by_whatsapp("")
        if not restaurant:
            agent_id = os.environ.get("AGENT_NAME") or "Serena"
            business_context = os.environ.get("BUSINESS_CONTEXT") or f"{agent_id} Core"
            restaurant = {
                "id": rid,
                "nome": business_context,
                "whatsapp_number": "",
                "endereco": "",
                "descricao": business_context,
                "capacidade_maxima_reserva": 8,
                "antecedencia_minima_horas": 2,
                "capacidade_total": 80,
                "ativo": True,
                "horarios": {},
                "faq": {},
                "cardapio": business_context,
                "datas_especiais": []
            }

    body_override = None
    if data.prompt_version_id is not None:
        v = await db.get_prompt_version(data.prompt_version_id)
        if not v:
            raise HTTPException(404, "Versão de prompt não encontrada")
        body_override = v["prompt_completo"]

    return await agent.test_turn(data.message, restaurant, body_override, user_phone=data.user_phone)

@app.get("/api/serena/prompts")
async def list_prompts():
    return await db.list_prompt_versions()

@app.get("/api/serena/prompts/active")
async def get_active_prompt():
    p = await db.get_active_prompt()
    if not p:
        raise HTTPException(404, "Nenhuma versão ativa")
    return p

@app.get("/api/serena/prompts/{pid}")
async def get_prompt(pid: int):
    p = await db.get_prompt_version(pid)
    if not p:
        raise HTTPException(404)
    return p

@app.post("/api/serena/prompts", status_code=201, dependencies=[Depends(require_admin)])
async def create_prompt(data: PromptCreate):
    pid = await db.insert_prompt_version(
        versao=data.versao,
        prompt_completo=data.prompt_completo,
        restaurant_id=data.restaurant_id,
        changelog=data.changelog,
        ativar=data.ativar,
    )
    return {"id": pid, "ativa": data.ativar, "restaurant_id": data.restaurant_id}

@app.post("/api/serena/prompts/{pid}/ativar", dependencies=[Depends(require_admin)])
async def activate_prompt(pid: int):
    p = await db.activate_prompt_version(pid)
    if not p:
        raise HTTPException(404)
    return p

@app.post("/api/serena/prompts/seed-v1", dependencies=[Depends(require_admin)])
async def seed_prompt_v1():
    """Insere a v1 = body fallback do agent.py se ainda não existir, e ativa."""
    from agent import _FALLBACK_BODY
    existing = await db.list_prompt_versions(limit=1)
    if existing:
        return {"ok": True, "skipped": True, "message": "Já existe versão. Use POST /api/serena/prompts."}
    pid = await db.insert_prompt_version(
        versao="v1",
        prompt_completo=_FALLBACK_BODY,
        restaurant_id="madonna_cucina",
        changelog="Versão inicial — extraída do hardcoded em agent.py",
        ativar=True,
    )
    return {"ok": True, "id": pid}


# ════════════════════════════════════════════════════════════════
# ORKESTRI — Executor de propostas de aprendizado
# ════════════════════════════════════════════════════════════════

async def _executar_proposta(proposta: dict, restaurant_id: str = "madonna_cucina") -> dict:
    """Aplica uma proposta de aprendizado aprovada ao prompt ativo do restaurante.

    Tipos suportados:
      faq          → anexa bloco FAQ ao final do prompt
      nova_intencao → anexa nova intenção à seção de intenções
      prompt_update → aplica melhoria geral ao prompt
      integracao    → sem alteração de prompt (registra apenas)
      treino        → sem alteração de prompt (registra apenas)
    """
    tipo = proposta.get("tipo", "")
    proposta_id = proposta["id"]
    titulo = proposta.get("titulo") or proposta.get("proposta", "")[:60]
    conteudo = proposta.get("proposta", "")

    # Tipos sem alteração de prompt
    if tipo in ("integracao", "treino"):
        return {"executado": False, "motivo": f"tipo '{tipo}' não requer alteração de prompt"}

    # Busca prompt ativo do restaurante correto
    ativo = await db.get_active_prompt(restaurant_id)
    if not ativo:
        return {"executado": False, "motivo": f"Nenhum prompt ativo para {restaurant_id}"}

    prompt_base = ativo["prompt_completo"]
    versao_base = ativo["versao"]

    # Monta o bloco a adicionar dependendo do tipo
    if tipo == "faq":
        bloco = f"\n\n# FAQ — APRENDIZADO AUTOMÁTICO ({titulo})\n{conteudo}"
    elif tipo == "nova_intencao":
        bloco = f"\n\n# NOVA INTENÇÃO — {titulo}\n{conteudo}"
    elif tipo == "prompt_update":
        bloco = f"\n\n# ATUALIZAÇÃO DE COMPORTAMENTO — {titulo}\n{conteudo}"
    else:
        bloco = f"\n\n# AJUSTE — {titulo}\n{conteudo}"

    novo_prompt = prompt_base + bloco

    # Gera próximo número de versão (ex: "v5" → "v6")
    import re as _re
    nums = _re.findall(r"\d+", str(versao_base))
    prox = int(nums[-1]) + 1 if nums else 1
    nova_versao = f"v{prox}"

    # Insere nova versão ativa — desativa apenas o prompt DO MESMO restaurante
    async with db.pool().acquire() as c:
        async with c.transaction():
            await c.execute(
                "UPDATE serena_prompt_versions SET ativa=FALSE "
                "WHERE ativa=TRUE AND restaurant_id=$1",
                restaurant_id,
            )
            row = await c.fetchrow("""
                INSERT INTO serena_prompt_versions
                  (versao, prompt_completo, changelog, ativa, proposta_id, aprovado_por, restaurant_id)
                VALUES ($1, $2, $3, TRUE, $4, $5, $6) RETURNING id""",
                nova_versao,
                novo_prompt,
                f"Executado automaticamente — proposta #{proposta_id} ({tipo}): {titulo}",
                proposta_id,
                "admin",
                restaurant_id,
            )
    db._prompt_cache_clear()
    return {
        "executado": True,
        "nova_versao": nova_versao,
        "prompt_version_id": row["id"],
        "tipo": tipo,
        "bloco_adicionado": bloco[:200],
    }


@app.post("/api/orkestri/propostas/{proposta_id}/aprovar",
          dependencies=[Depends(require_admin)])
async def aprovar_proposta(proposta_id: int):
    """Aprova uma proposta e dispara o executor de prompt."""
    async with db.pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM orkestri_learning WHERE id=$1", proposta_id)
    if not row:
        raise HTTPException(404, detail="Proposta não encontrada")
    proposta = dict(row)
    if proposta["status"] != "pending":
        raise HTTPException(400, detail=f"Proposta já está '{proposta['status']}'")

    # Marca como aprovada
    async with db.pool().acquire() as c:
        await c.execute(
            "UPDATE orkestri_learning SET status='approved' WHERE id=$1", proposta_id)

    # Executa
    resultado = await _executar_proposta(proposta)
    return {"ok": True, "proposta_id": proposta_id, **resultado}


@app.post("/api/orkestri/propostas/{proposta_id}/descartar",
          dependencies=[Depends(require_admin)])
async def descartar_proposta(proposta_id: int):
    """Descarta uma proposta de aprendizado."""
    async with db.pool().acquire() as c:
        row = await c.fetchrow(
            "SELECT id, status FROM orkestri_learning WHERE id=$1", proposta_id)
    if not row:
        raise HTTPException(404, detail="Proposta não encontrada")
    if row["status"] != "pending":
        raise HTTPException(400, detail=f"Proposta já está '{row['status']}'")
    async with db.pool().acquire() as c:
        await c.execute(
            "UPDATE orkestri_learning SET status='dismissed' WHERE id=$1", proposta_id)
    return {"ok": True, "proposta_id": proposta_id, "status": "dismissed"}


@app.get("/api/orkestri/historico-prompts",
         dependencies=[Depends(require_admin)])
async def historico_prompts(limit: int = 30):
    """Lista versões do prompt com proposta de origem."""
    async with db.pool().acquire() as c:
        rows = await c.fetch("""
            SELECT
                spv.id, spv.versao, spv.changelog, spv.ativa,
                spv.criado_em, spv.aprovado_por,
                spv.proposta_id,
                ol.titulo AS proposta_titulo,
                ol.tipo   AS proposta_tipo,
                LEFT(spv.prompt_completo, 200) AS preview
            FROM serena_prompt_versions spv
            LEFT JOIN orkestri_learning ol ON ol.id = spv.proposta_id
            ORDER BY spv.criado_em DESC
            LIMIT $1""", limit)
    return [dict(r) for r in rows]


# ── Weekly report (gera análise via Claude) ───────────────────

@app.post("/api/serena/weekly-report", dependencies=[Depends(require_admin)])
async def generate_weekly_report(dias: int = 7):
    """Gera análise do período via Claude e persiste em serena_weekly_reports.

    Reusável: a mesma função roda no cron (segunda 09h BRT, em main.lifespan).
    """
    import serena_weekly
    return await serena_weekly.generate_weekly_report(dias=dias)

@app.get("/api/serena/weekly-report", dependencies=[Depends(require_admin)])
async def list_weekly_reports():
    return await db.list_weekly_reports()


# ════════════════════════════════════════════════════════════════
# INSIGHTS — análises agregadas para o Dashboard
# ════════════════════════════════════════════════════════════════

@app.get("/api/insights")
async def get_insights(rid: Optional[str] = None):
    key = f"insights:{rid or '_'}"
    if key in _insights_cache:
        return _insights_cache[key]
    data = await db.insights_aggregate(rid)
    _insights_cache[key] = data
    return data


# ════════════════════════════════════════════════════════════════
# ORDENS DE SERVIÇO
# ════════════════════════════════════════════════════════════════

@app.get("/api/os/{restaurant_id}", dependencies=[Depends(require_admin)])
async def listar_os(restaurant_id: str, status: str | None = None):
    return await db.listar_os(restaurant_id, status)

@app.post("/api/os/{restaurant_id}", dependencies=[Depends(require_admin)])
async def criar_os(restaurant_id: str, data: dict = Body(...)):
    data["restaurant_id"] = restaurant_id
    return await db.criar_os(data)

@app.get("/api/os/{restaurant_id}/{os_id}", dependencies=[Depends(require_admin)])
async def get_os(restaurant_id: str, os_id: str):
    os = await db.get_os(os_id, restaurant_id)
    if not os:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    return os

@app.patch("/api/os/{restaurant_id}/{os_id}", dependencies=[Depends(require_admin)])
async def atualizar_os(restaurant_id: str, os_id: str, data: dict = Body(...)):
    result = await db.atualizar_os(os_id, restaurant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="OS não encontrada")
    # Fire-and-forget: email de proposta quando status muda para proposta_enviada
    if data.get("status") == "proposta_enviada":
        try:
            asyncio.create_task(send_proposta_enviada(dict(result)))
        except Exception as _e:
            print(f"[email] erro ao disparar proposta_enviada: {_e!r}")
    return result

@app.post("/api/os/{restaurant_id}/{os_id}/checkout", dependencies=[Depends(require_admin)])
async def criar_checkout_os(restaurant_id: str, os_id: str):
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe não configurado")

    os_data = await db.get_os(os_id, restaurant_id)
    if not os_data:
        raise HTTPException(status_code=404, detail="OS não encontrada")

    if not os_data.get("valor_entrada"):
        raise HTTPException(status_code=422, detail="valor_entrada obrigatório para gerar checkout")

    painel_url = os.environ.get("PAINEL_URL", "https://madonna-painel.vercel.app")
    import asyncio
    session = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "brl",
                    "product_data": {
                        "name": f"Entrada — {os_data['tipo_evento']}",
                        "description": f"{os_data['pessoas']} pessoas · {os_data['data']}",
                    },
                    "unit_amount": int(float(os_data["valor_entrada"]) * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{painel_url}/os?payment=success",
            cancel_url=f"{painel_url}/os?payment=cancelled",
            metadata={"os_id": os_id, "restaurant_id": restaurant_id},
        )
    )

    await db.atualizar_os(os_id, restaurant_id, {
        "stripe_checkout_session_id": session.id
    })

    return {"checkout_url": session.url, "session_id": session.id}


@app.post("/api/os/{restaurant_id}/{os_id}/pagamento/link", dependencies=[Depends(require_admin)])
async def gerar_link_pagamento(restaurant_id: str, os_id: str, data: dict = Body(default={})):
    """Gera um Stripe Payment Link para a OS com tipo: entrada | total | saldo."""
    import stripe as _stripe, asyncio

    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not _stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe não configurado")

    os_data = await db.get_os(os_id, restaurant_id)
    if not os_data:
        raise HTTPException(status_code=404, detail="OS não encontrada")

    tipo = data.get("tipo", "entrada")
    if tipo not in ("entrada", "total", "saldo"):
        raise HTTPException(status_code=422, detail="tipo deve ser 'entrada', 'total' ou 'saldo'")

    valor_entrada = float(os_data.get("valor_entrada") or 0)
    valor_total   = float(os_data.get("valor_total")   or 0)

    if tipo == "entrada":
        valor = valor_entrada
        desc  = "Entrada"
    elif tipo == "total":
        valor = valor_total
        desc  = "Total"
    else:
        valor = max(valor_total - valor_entrada, 0)
        desc  = "Saldo restante"

    if valor <= 0:
        raise HTTPException(status_code=422, detail=f"Valor para '{tipo}' é zero ou inválido")

    amount_cents = int(round(valor * 100))
    nome_produto = f"{desc} — {os_data.get('tipo_evento', 'Evento')}"
    desc_produto = f"{os_data.get('pessoas', '—')} pessoas · {os_data.get('data', '—')}"

    def _create_link():
        price = _stripe.Price.create(
            currency="brl",
            unit_amount=amount_cents,
            product_data={
                "name": nome_produto,
                "metadata": {"os_id": os_id, "restaurant_id": restaurant_id},
            },
        )
        link = _stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            metadata={"os_id": os_id, "restaurant_id": restaurant_id, "tipo": tipo},
            after_completion={"type": "redirect",
                              "redirect": {"url": f"{os.environ.get('PAINEL_URL', 'https://madonna-painel.vercel.app')}/os?payment=success"}},
        )
        return link

    link = await asyncio.get_event_loop().run_in_executor(None, _create_link)
    return {"url": link.url, "id": link.id, "tipo": tipo, "valor": valor}


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Assinatura do webhook inválida")
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook inválido")

    # Usar JSON bruto — StripeObject não expõe .get() em SDK v7
    import json as _json
    event_dict = _json.loads(payload)

    if event["type"] == "checkout.session.completed":
        session = event_dict["data"]["object"]   # plain dict, .get() funciona normalmente
        metadata = session.get("metadata") or {}
        os_id = metadata.get("os_id")
        rid = metadata.get("restaurant_id")
        payment_intent = session.get("payment_intent")
        amount_received = session.get("amount_total")  # em centavos
        if os_id and rid:
            await db.atualizar_os(os_id, rid, {
                "status": "entrada_paga",
                "stripe_payment_intent_id": payment_intent,
            })
            # TODO sprint6-email: descomentar quando send_comprovante_pagamento estiver
            # integrado com campos de cliente_email na OS.
            # try:
            #     os_data = await db.get_os(os_id, rid)
            #     if os_data:
            #         valor_pago = (amount_received or 0) / 100.0
            #         asyncio.create_task(send_comprovante_pagamento(dict(os_data), valor_pago))
            # except Exception as _e:
            #     print(f"[email] erro ao disparar comprovante_pagamento: {_e!r}")

    return {"ok": True}


# ── Checklists D-7 / D-0 ─────────────────────────────────────

@app.get("/api/os/{restaurant_id}/{os_id}/checklist", dependencies=[Depends(require_admin)])
async def get_checklist_os(restaurant_id: str, os_id: str, tipo: str = "d7"):
    if tipo not in ("d7", "d0"):
        raise HTTPException(status_code=422, detail="tipo deve ser 'd7' ou 'd0'")
    items = await db.get_or_create_checklist(os_id, tipo)
    return items

@app.patch("/api/os/{restaurant_id}/{os_id}/checklist/{item_id}", dependencies=[Depends(require_admin)])
async def patch_checklist_item(restaurant_id: str, os_id: str, item_id: str, data: dict = Body(default={})):
    result = await db.toggle_checklist_item(item_id, data.get("concluido_por", "equipe"))
    if not result:
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado")
    return result


# ════════════════════════════════════════════════════════════════
# FINANCEIRO
# ════════════════════════════════════════════════════════════════

@app.get("/api/financeiro/{restaurant_id}", dependencies=[Depends(require_admin)])
async def get_financeiro(restaurant_id: str, periodo: str = "mes"):
    """Resumo financeiro das OS por período: semana | mes | trimestre."""
    if periodo not in ("semana", "mes", "trimestre"):
        raise HTTPException(422, "periodo deve ser semana, mes ou trimestre")
    return await db.get_financeiro_resumo(restaurant_id, periodo)


@app.post("/api/restaurants/{rid}/ltv/recalcular", dependencies=[Depends(require_admin)])
async def recalcular_ltv(rid: str):
    """Recalcula LTV de todos os contatos do restaurante combinando reservas + OS."""
    resultado = await db.recalcular_ltv(rid)
    return resultado


@app.get("/api/restaurants/{rid}/reports/pipeline", dependencies=[Depends(require_admin)])
async def get_pipeline(rid: str):
    """Pipeline comercial: funil OS por status com valores + reservas do mês."""
    return await db.get_pipeline_report(rid)


@app.get("/api/restaurants/{rid}/handoff/sla-stats", dependencies=[Depends(require_admin)])
async def get_handoff_sla(rid: str):
    """SLA de handoff: abertos, vencidos (>2h), TMA e taxa dentro do SLA."""
    return await db.get_handoff_sla_stats(rid)


# ════════════════════════════════════════════════════════════════
# WIDGET DE RESERVA — endpoint público com rate limiting
# ════════════════════════════════════════════════════════════════

import time as _time
from collections import defaultdict as _defaultdict

_widget_hits: dict[str, list[float]] = _defaultdict(list)
_WIDGET_RPM = 10  # requests por minuto por IP

def _widget_rate_ok(ip: str) -> bool:
    now = _time.time()
    _widget_hits[ip] = [t for t in _widget_hits[ip] if now - t < 60]
    if len(_widget_hits[ip]) >= _WIDGET_RPM:
        return False
    _widget_hits[ip].append(now)
    return True


class WidgetReservaIn(BaseModel):
    nome:        str
    telefone:    str
    tipo_evento: str
    data:        str
    pessoas:     int
    observacoes: Optional[str] = None


@app.post("/api/widget/reserva/{restaurant_id}")
async def widget_reserva(
    restaurant_id: str,
    body: WidgetReservaIn,
    request: Request,
):
    ip = request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()
    if not _widget_rate_ok(ip):
        raise HTTPException(status_code=429, detail="Muitas solicitações. Tente novamente em alguns instantes.")

    # Persiste o contato (cria ou atualiza nome)
    telefone = "".join(filter(str.isdigit, body.telefone))
    if not telefone.startswith("55"):
        telefone = "55" + telefone

    try:
        await db.ensure_contact(telefone, body.nome)
    except Exception:
        pass  # não bloqueia o fluxo se o contato já existir

    # Cria handoff para a equipe revisar o pedido
    motivo = (
        f"Pedido via widget — {body.tipo_evento} · {body.data} · "
        f"{body.pessoas} pax · {body.observacoes or 'sem observações'}"
    )
    try:
        await db.create_handoff(telefone, restaurant_id, motivo)
    except Exception:
        pass

    print(f"[WIDGET] {restaurant_id} | {telefone} | {body.tipo_evento} | {body.data}")
    return {"ok": True, "mensagem": "Pedido recebido! Nossa equipe entrará em contato em breve."}


# ════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ════════════════════════════════════════════════════════════════

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "sprint": "11", "release": "sprint11-prompt-fix"}

def _twiml(text: str) -> PlainTextResponse:
    safe = saxutils.escape(text)
    return PlainTextResponse(
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>',
        media_type="text/xml")

def _twiml_ack() -> PlainTextResponse:
    """TwiML vazio — apenas confirma recebimento ao Twilio sem enviar mensagem.
    Usado quando a resposta ao cliente será enviada via outbound (send_to_customer)."""
    return PlainTextResponse(
        '<?xml version="1.0" encoding="UTF-8"?><Response/>',
        media_type="text/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
