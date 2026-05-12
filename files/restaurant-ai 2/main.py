"""
FastAPI — WhatsApp webhook + API REST completa para o painel.
"""

import os
import xml.sax.saxutils as saxutils
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
import database as db
from agent import RestaurantAgent
from models import (
    RestaurantCreate, RestaurantUpdate, BusinessHourItem,
    MenuItemCreate, MenuItemUpdate, FaqItemCreate,
    ReservationUpdate, HandoffReply, HandoffResolve, TeamMemberCreate
)
import notifications as notif

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await db.close_db()

app = FastAPI(title="Restaurant AI — API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
agent = RestaurantAgent()


# ════════════════════════════════════════════════════════════════
# WHATSAPP WEBHOOK
# ════════════════════════════════════════════════════════════════

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...), Body: str = Form(""), To: str = Form(...)
):
    message = Body.strip()
    if not message:
        return _twiml("")

    user_phone       = From.replace("whatsapp:", "").strip()
    restaurant_phone = To.replace("whatsapp:", "").strip()

    response_text = await agent.process(user_phone, restaurant_phone, message)

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
    r = await db.get_restaurant_full(rid)
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
    sessions = await db.get_handoff_sessions("", None)
    session = next((s for s in sessions if s["id"] == hid), None)
    if not session:
        raise HTTPException(404)

    restaurant = await db.get_restaurant_full(session["restaurant_id"])
    notif.send_to_customer(
        restaurant["whatsapp_number"],
        session["user_phone"],
        data.mensagem,
    )
    await db.save_message(session["user_phone"], session["restaurant_id"],
                          "assistant", f"[{data.atendente_nome}] {data.mensagem}")
    await db.update_handoff_status(hid, "em_atendimento", data.atendente_nome)
    return {"ok": True}

@app.post("/api/handoff/{hid}/resolve")
async def handoff_resolve(hid: int, data: HandoffResolve):
    await db.update_handoff_status(hid, "resolvido", data.atendente_nome)
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


# ════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ════════════════════════════════════════════════════════════════

@app.get("/health")
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
