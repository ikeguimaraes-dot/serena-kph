"""
FastAPI — WhatsApp webhook + API REST completa para o painel.
"""

import os
import asyncio
import xml.sax.saxutils as saxutils
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Form, HTTPException, Header, Depends
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


# ════════════════════════════════════════════════════════════════
# WHATSAPP WEBHOOK
# ════════════════════════════════════════════════════════════════

MAX_MSG_LEN = 2000

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...), Body: str = Form(""), To: str = Form(...),
    ProfileName: str = Form(""),
    secret: Optional[str] = None,
    x_webhook_secret: Optional[str] = Header(None),
):
    expected_secret = os.environ.get("WEBHOOK_SECRET")
    if expected_secret:
        if secret != expected_secret and x_webhook_secret != expected_secret:
            print(f"[WEBHOOK] Acesso negado: WEBHOOK_SECRET incorreto")
            raise HTTPException(403, "Acesso negado: webhook secret inválido")

    print(f"[WEBHOOK] From={From!r} To={To!r} ProfileName={ProfileName!r} Body={Body!r}")
    message = Body.strip()
    if not message:
        return _twiml("")
    if len(message) > MAX_MSG_LEN:
        print(f"[WEBHOOK] mensagem descartada: tamanho {len(message)} > {MAX_MSG_LEN}")
        return _twiml("Mensagem muito longa. Por favor, envie uma mensagem mais curta.")

    user_phone       = From.replace("whatsapp:", "").strip()
    restaurant_phone = To.replace("whatsapp:", "").strip()
    print(f"[WEBHOOK] user_phone={user_phone!r} restaurant_phone={restaurant_phone!r}")
    print(f"[WEBHOOK] ProfileName='{ProfileName}' user_phone='{user_phone}'")

    response_text = await agent.process(user_phone, restaurant_phone, message, profile_name=ProfileName)

    # None = conversa em modo handoff, equipe já foi notificada
    if response_text is None:
        return _twiml("Mensagem recebida. Nosso atendente vai responder em instantes.")

    return _twiml(response_text)


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

@app.get("/api/restaurants/{rid}/handoff")
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

@app.post("/api/agenda/{restaurant_id}/reservas", status_code=201)
async def nova_reserva(restaurant_id: str, body: dict):
    """Cria nova reserva. Verifica disponibilidade antes."""
    body["restaurant_id"] = restaurant_id
    disponivel = await db.check_disponibilidade(
        restaurant_id, body["data"], body["turno_id"], body["posicoes"]
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

@app.patch("/api/agenda/{restaurant_id}/reservas/{reserva_id}/cancelar")
async def cancelar(restaurant_id: str, reserva_id: str):
    ok = await db.cancelar_reserva(reserva_id, restaurant_id)
    if not ok:
        raise HTTPException(404, "Reserva não encontrada ou já cancelada")
    return {"ok": True}


# ════════════════════════════════════════════════════════════════
# CONVERSAS
# ════════════════════════════════════════════════════════════════

@app.get("/api/restaurants/{rid}/conversations")
async def list_conversations(rid: str):
    return await db.get_conversations_list(rid)

@app.get("/api/conversations/{user_phone}")
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

@app.get("/api/contacts")
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

@app.get("/api/contacts/search")
async def search_contacts(q: str, limit: int = 50):
    return await db.search_contacts(q, limit=limit)

@app.get("/api/contacts/stats")
async def contact_stats():
    return await db.contact_stats()

@app.post("/api/contacts/mark-inactive")
async def contacts_mark_inactive(threshold_days: int = 45):
    """Move para 'Inativo' contatos sem visita há N+ dias. Cron-only — exige x-admin-secret."""
    affected = await db.mark_inactive_contacts(threshold_days)
    return {"affected": affected}

@app.get("/api/contacts/{celular}")
async def get_contact(celular: str):
    c = await db.get_contact(celular)
    if not c:
        raise HTTPException(404, "Contato não encontrado")
    return c

@app.get("/api/contacts/{celular}/reservations")
async def contact_reservations(celular: str, limit: int = 20):
    return await db.get_contact_reservations(celular, limit=limit)

@app.get("/api/contacts/{celular}/conversations")
async def contact_conversations(celular: str, limit: int = 100):
    return await db.get_contact_conversations(celular, limit=limit)

@app.patch("/api/contacts/{celular}")
async def patch_contact(celular: str, data: ContactUpdate):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    c = await db.update_contact(celular, payload)
    if not c:
        raise HTTPException(404)
    return c

@app.patch("/api/contacts/{celular}/kanban")
async def move_kanban(celular: str, data: ContactKanbanMove):
    try:
        c = await db.move_contact_kanban(celular, data.estagio_kanban)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not c:
        raise HTTPException(404)
    return c


@app.get("/api/contacts/{celular}/profile")
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

@app.get("/api/serena/metrics")
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

@app.get("/api/serena/custo")
async def serena_custo(periodo: str = "mtd"):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_custo(_periodo_to_days(periodo), restaurant_id=rid)

@app.get("/api/serena/recent")
async def serena_recent(limit: int = 100, only_handoffs: bool = False):
    agent_id = os.environ.get("AGENT_NAME")
    rid = agent_id.lower().strip() if agent_id else None
    return await db.serena_recent(limit=limit, only_handoffs=only_handoffs, restaurant_id=rid)

@app.get("/api/serena/training-export")
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


# ── Versionamento de prompt ────────────────────────────────────

class PromptCreate(BaseModel):
    versao: str
    prompt_completo: str
    changelog: Optional[str] = None
    ativar: bool = False

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
        changelog=data.changelog,
        ativar=data.ativar,
    )
    return {"id": pid, "ativa": data.ativar}

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
        changelog="Versão inicial — extraída do hardcoded em agent.py",
        ativar=True,
    )
    return {"ok": True, "id": pid}


# ── Weekly report (gera análise via Claude) ───────────────────

@app.post("/api/serena/weekly-report")
async def generate_weekly_report(dias: int = 7):
    """Gera análise do período via Claude e persiste em serena_weekly_reports.

    Reusável: a mesma função roda no cron (segunda 09h BRT, em main.lifespan).
    """
    import serena_weekly
    return await serena_weekly.generate_weekly_report(dias=dias)

@app.get("/api/serena/weekly-report")
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
# UTILITÁRIOS
# ════════════════════════════════════════════════════════════════

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}

def _twiml(text: str) -> PlainTextResponse:
    safe = saxutils.escape(text)
    return PlainTextResponse(
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>',
        media_type="text/xml")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
