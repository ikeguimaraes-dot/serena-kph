import re
from datetime import date
from typing import Optional
from tagme_handlers import handle_consultar_reserva, handle_fazer_reserva, handle_cancelar_reserva

INTENT_CONSULTAR = re.compile(r"(minha reserva|tenho reserva|verificar reserva|checar reserva|tem reserva|ver minha reserva|confirmar reserva|reserva hoje|reserva amanhã|minhas reservas)", re.IGNORECASE)
INTENT_FAZER = re.compile(r"(quero reservar|fazer uma reserva|quero uma mesa|reservar mesa|fazer reserva|nova reserva|agendar|marcar mesa|reservar)", re.IGNORECASE)
INTENT_CANCELAR = re.compile(r"(cancelar reserva|quero cancelar|cancela minha|desmarcar|cancela a reserva|não vou mais|desistir da reserva)", re.IGNORECASE)

def detect_intent(message: str) -> Optional[str]:
    if INTENT_CANCELAR.search(message): return "CANCELAR_RESERVA"
    if INTENT_FAZER.search(message): return "FAZER_RESERVA"
    if INTENT_CONSULTAR.search(message): return "CONSULTAR_RESERVA"
    return None

async def route_tagme_intent(message: str, phone: str, session: dict) -> Optional[str]:
    intent = detect_intent(message)
    if intent is None: return None
    if intent == "CONSULTAR_RESERVA":
        filter_date = date.today() if "hoje" in message.lower() else None
        return await handle_consultar_reserva(phone, filter_date=filter_date)
    if intent == "FAZER_RESERVA":
        return await handle_fazer_reserva(phone=phone, name=session.get("name"), date_str=session.get("reservation_date"), time_str=session.get("reservation_time"), party_size=session.get("party_size"), observation=session.get("observation"))
    if intent == "CANCELAR_RESERVA":
        return await handle_cancelar_reserva(phone=phone, reservation_id=session.get("reservation_id"))
    return None
