"""
Notificações via Twilio WhatsApp para a equipe.
Adicione TWILIO_* no .env para ativar.
"""

import os
from typing import Optional

def _client():
    try:
        from twilio.rest import Client
        return Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    except Exception:
        return None

def notify_handoff(
    team_whatsapp: str,
    restaurant_nome: str,
    customer_phone: str,
    motivo: str,
    resumo: str,
):
    """Avisa a equipe quando há transferência para humano."""
    client = _client()
    if not client:
        print(f"[HANDOFF] {restaurant_nome} | {customer_phone} | {motivo}")
        return

    body = (
        f"🚨 *Atendimento humano solicitado*\n\n"
        f"Restaurante: {restaurant_nome}\n"
        f"Cliente: {customer_phone}\n"
        f"Motivo: {motivo}\n\n"
        f"Contexto:\n{resumo}\n\n"
        f"Acesse o painel ou contate o cliente diretamente."
    )
    client.messages.create(
        from_=f"whatsapp:{os.environ.get('TWILIO_FROM_NUMBER','')}",
        to=f"whatsapp:{team_whatsapp}",
        body=body,
    )

def send_to_customer(restaurant_number: str, customer_phone: str, message: str):
    """Envia mensagem do atendente para o cliente via Twilio."""
    client = _client()
    if not client:
        print(f"[MSG → {customer_phone}]: {message}")
        return
    client.messages.create(
        from_=f"whatsapp:{restaurant_number}",
        to=f"whatsapp:{customer_phone}",
        body=message,
    )
