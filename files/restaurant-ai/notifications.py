"""
Notificações via Twilio WhatsApp para a equipe.
Adicione TWILIO_* no .env para ativar.
"""

import os
from typing import Optional

_twilio_client = None

def _client():
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client
    try:
        from twilio.rest import Client
        sid = os.environ.get("TWILIO_ACCOUNT_SID")
        token = os.environ.get("TWILIO_AUTH_TOKEN")
        if not sid or not token:
            return None
        _twilio_client = Client(sid, token)
        return _twilio_client
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
    """Envia mensagem do atendente para o cliente via Twilio.

    Usa TWILIO_FROM_NUMBER (sender autorizado na Twilio) como remetente.
    Cai em restaurant_number só se TWILIO_FROM_NUMBER não estiver configurado.
    """
    client = _client()
    if not client:
        print(f"[MSG → {customer_phone}] (Twilio não configurado): {message[:80]}")
        return
    sender = os.environ.get("TWILIO_FROM_NUMBER") or restaurant_number
    try:
        msg = client.messages.create(
            from_=f"whatsapp:{sender}",
            to=f"whatsapp:{customer_phone}",
            body=message,
        )
        print(f"[MSG → {customer_phone}] Twilio OK sid={msg.sid}")
    except Exception as e:
        print(f"[MSG → {customer_phone}] Twilio FALHOU from={sender!r}: {e!r}")
